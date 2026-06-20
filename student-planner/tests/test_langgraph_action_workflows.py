import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.contracts import DBWritePlan, PendingConfirmation
from app.agent.langgraph_loop import prepare_langgraph_state, run_langgraph_agent_loop, run_langgraph_tool_node
from app.models.course import Course
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services.schedule_upload_cache import store_schedule_upload
from app.agent.tool_executor import execute_tool as real_execute_tool
from tests.conftest import TestSession


def stream_response_chunks(*, response: dict):
    async def _generator():
        yield {"type": "response", "response": response}

    return _generator()


async def collect_events(generator, *, answers: list[str] | None = None) -> list[dict]:
    pending_answers = list(answers or [])
    events: list[dict] = []
    event = await generator.__anext__()
    while True:
        events.append(event)
        try:
            if event["type"] == "ask_user":
                answer = pending_answers.pop(0) if pending_answers else "确认"
                event = await generator.asend(answer)
            else:
                event = await generator.__anext__()
        except StopAsyncIteration:
            break
    return events


def assert_native_action_graph(state: dict, route: str) -> None:
    assert state["route"] == route
    assert state["should_delegate_legacy_loop"] is False
    assert route in state["graph_nodes"]
    assert "delegate_legacy_loop" not in state["graph_nodes"]


def graph_nodes_from_tool_results(events: list[dict]) -> list[str]:
    nodes: list[str] = []
    for event in events:
        result = event.get("result")
        if isinstance(result, dict) and isinstance(result.get("graph_nodes"), list):
            nodes.extend(str(node) for node in result["graph_nodes"])
    return nodes


@pytest.mark.asyncio
async def test_langgraph_plain_text_ask_fallback_uses_tool_node_state(setup_db):
    from app.agent import langgraph_loop as langgraph_runtime

    mock_client = AsyncMock()
    llm_call_count = 0
    tool_node_outputs: list[dict] = []
    resumed_states: list[dict] = []
    original_resume = langgraph_runtime.resume_langgraph_ask_user_state

    def mock_chat_completion_stream(client, messages, tools=None, tool_choice=None):
        nonlocal llm_call_count
        llm_call_count += 1
        if llm_call_count == 1:
            return stream_response_chunks(
                response={"role": "assistant", "content": "请告诉我是哪天、几点，以及是否需要提前提醒？"}
            )
        return stream_response_chunks(response={"role": "assistant", "content": "收到。"})

    async def direct_execute_spy(tool_name, tool_args, db, user_id):
        if tool_name == "ask_user":
            raise AssertionError("plain-text ask fallback must use run_langgraph_tool_node")
        return await real_execute_tool(tool_name, tool_args, db, user_id)

    async def spy_run_langgraph_tool_node(state, runtime):
        next_state = await run_langgraph_tool_node(state, runtime)
        tool_node_outputs.append(dict(next_state))
        return next_state

    def spy_resume_langgraph_ask_user_state(state, *, user_response):
        next_state = original_resume(state, user_response=user_response)
        resumed_states.append(dict(next_state))
        return next_state

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.loop.execute_tool", side_effect=direct_execute_spy),
        patch("app.agent.langgraph_loop.run_langgraph_tool_node", side_effect=spy_run_langgraph_tool_node),
        patch(
            "app.agent.langgraph_loop.resume_langgraph_ask_user_state",
            side_effect=spy_resume_langgraph_ask_user_state,
        ),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Plain-text ask action route should not delegate to run_agent_loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-lg-plain-ask", username="lg-plain-ask", hashed_password="x")
            db.add(user)
            await db.commit()

            events = await collect_events(
                run_langgraph_agent_loop("提醒我买牛奶", user, "session-lg-plain-ask", db, mock_client),
                answers=["2099-06-01 10:00-10:30，不提醒"],
            )

    assert [event["type"] for event in events] == ["tool_call", "ask_user", "text", "done"]
    assert tool_node_outputs[0]["pending_ask"]["status"] == "awaiting_answer"
    assert tool_node_outputs[0]["pending_ask"]["tool_name"] == "ask_user"
    assert resumed_states[0]["submitted_answer"] == "2099-06-01 10:00-10:30，不提醒"
    assert resumed_states[0]["pending_ask"]["status"] == "answered"
    assert resumed_states[0]["tool_history"] == ["ask_user"]


@pytest.mark.asyncio
async def test_langgraph_missing_task_shortcut_records_confirmation_state(setup_db):
    from app.agent import langgraph_loop as langgraph_runtime

    mock_client = AsyncMock()
    recorded_pause_states: list[dict] = []
    resumed_states: list[dict] = []
    original_record = langgraph_runtime.record_langgraph_ask_user_pause_state
    original_resume = langgraph_runtime.resume_langgraph_ask_user_state

    def spy_record_langgraph_ask_user_pause_state(state, **kwargs):
        next_state = original_record(state, **kwargs)
        recorded_pause_states.append(dict(next_state))
        return next_state

    def spy_resume_langgraph_ask_user_state(state, *, user_response):
        next_state = original_resume(state, user_response=user_response)
        resumed_states.append(dict(next_state))
        return next_state

    with (
        patch(
            "app.agent.loop.chat_completion_stream",
            side_effect=AssertionError("Missing-task shortcut should not call the LLM"),
        ),
        patch("app.agent.langgraph_loop.record_langgraph_ask_user_pause_state", side_effect=spy_record_langgraph_ask_user_pause_state),
        patch(
            "app.agent.langgraph_loop.resume_langgraph_ask_user_state",
            side_effect=spy_resume_langgraph_ask_user_state,
        ),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Missing-task shortcut should not delegate to run_agent_loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-lg-shortcut-confirm", username="lg-shortcut-confirm", hashed_password="x")
            db.add(user)
            await db.commit()

            confirm_events = await collect_events(
                run_langgraph_agent_loop("创建Shortcut task任务", user, "session-lg-shortcut-confirm", db, mock_client),
                answers=["2099-06-01 10:00-10:30，不提醒", "确认"],
            )
            task_result = await db.execute(select(Task).where(Task.user_id == user.id))
            confirmed_tasks = list(task_result.scalars().all())
            confirm_pause_states = list(recorded_pause_states)
            confirm_resumed_states = list(resumed_states)

            recorded_pause_states.clear()
            resumed_states.clear()
            cancel_events = await collect_events(
                run_langgraph_agent_loop("创建Cancelled shortcut任务", user, "session-lg-shortcut-cancel", db, mock_client),
                answers=["2099-06-02 10:00-10:30，不提醒", "取消"],
            )
            task_result = await db.execute(select(Task).where(Task.user_id == user.id))
            all_tasks = list(task_result.scalars().all())
            cancel_pause_states = list(recorded_pause_states)
            cancel_resumed_states = list(resumed_states)

    assert [event["type"] for event in confirm_events] == [
        "ask_user",
        "ask_user",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert confirmed_tasks[0].title == "Shortcut task"
    assert confirm_pause_states[0]["pending_ask"]["status"] == "awaiting_answer"
    assert confirm_pause_states[1]["pending_ask"]["status"] == "awaiting_answer"
    assert isinstance(confirm_pause_states[1]["pending_confirmation"], PendingConfirmation)
    assert isinstance(confirm_pause_states[1]["db_write_plan"], DBWritePlan)
    assert confirm_pause_states[1]["db_write_plan"].tool_name == "create_task"
    assert confirm_resumed_states[1]["submitted_answer"] == "确认"

    assert [event["type"] for event in cancel_events] == ["ask_user", "ask_user", "text", "done"]
    assert len(all_tasks) == 1
    assert all_tasks[0].title == "Shortcut task"
    assert cancel_pause_states[1]["pending_ask"]["status"] == "awaiting_answer"
    assert isinstance(cancel_pause_states[1]["pending_confirmation"], PendingConfirmation)
    assert isinstance(cancel_pause_states[1]["db_write_plan"], DBWritePlan)
    assert cancel_resumed_states[1]["submitted_answer"] == "取消"


@pytest.mark.asyncio
async def test_langgraph_native_task_reminder_confirmed_write_does_not_delegate(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0
    tool_node_inputs: list[dict] = []
    tool_node_outputs: list[dict] = []

    def mock_chat_completion_stream(client, messages, tools=None, tool_choice=None):
        nonlocal llm_call_count
        llm_call_count += 1

        if llm_call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "ask_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": json.dumps(
                                    {
                                        "question": "确认创建任务：做饭，2026-05-02 17:00-17:30，并在17:00提醒。",
                                        "type": "confirm",
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 2:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "create_1",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": json.dumps(
                                    {
                                        "title": "做饭",
                                        "scheduled_date": "2026-05-02",
                                        "start_time": "17:00",
                                        "end_time": "17:30",
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 3:
            tool_messages = [str(message.get("content") or "") for message in messages if message.get("role") == "tool"]
            task_id = next(
                content.split('"id": "')[1].split('"', 1)[0]
                for content in tool_messages
                if '"status": "created"' in content
            )
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "reminder_1",
                            "type": "function",
                            "function": {
                                "name": "set_reminder",
                                "arguments": json.dumps(
                                    {
                                        "target_type": "task",
                                        "target_id": task_id,
                                        "advance_minutes": 0,
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(response={"role": "assistant", "content": "已经帮你创建做饭任务，并设置提醒。"})

    prompt = "17.00提醒我去做饭"
    state = await prepare_langgraph_state(prompt)
    assert_native_action_graph(state, "tool_workflow")
    assert "task_tool_node" in state["graph_nodes"]
    assert "ask_user_pause" in state["graph_nodes"]
    assert "confirmed_write" in state["graph_nodes"]

    async def spy_run_langgraph_tool_node(state, runtime):
        tool_node_inputs.append(dict(state))
        next_state = await run_langgraph_tool_node(state, runtime)
        tool_node_outputs.append(dict(next_state))
        return next_state

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.langgraph_loop.run_langgraph_tool_node", side_effect=spy_run_langgraph_tool_node) as tool_node_spy,
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Task/reminder action route should not delegate to run_agent_loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-lg-task-reminder", username="lg-task-reminder", hashed_password="x")
            db.add(user)
            await db.commit()

            events = await collect_events(
                run_langgraph_agent_loop(prompt, user, "session-lg-task-reminder", db, mock_client),
                answers=["可以"],
            )

            task_result = await db.execute(select(Task).where(Task.user_id == user.id))
            tasks = list(task_result.scalars().all())
            reminder_result = await db.execute(select(Reminder).where(Reminder.user_id == user.id))
            reminders = list(reminder_result.scalars().all())

    assert [event["type"] for event in events] == [
        "tool_call",
        "ask_user",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert [event["name"] for event in events if event["type"] == "tool_call"] == [
        "ask_user",
        "create_task",
        "set_reminder",
    ]
    event_graph_nodes = graph_nodes_from_tool_results(events)
    assert "task_tool_node" in event_graph_nodes
    assert "ask_user_pause" in event_graph_nodes
    assert "confirmed_write" in event_graph_nodes
    assert tool_node_spy.await_count == 3
    assert tool_node_outputs[0]["pending_ask"]["status"] == "awaiting_answer"
    assert tool_node_outputs[0]["resume_state"]["status"] == "awaiting_answer"
    assert tool_node_inputs[1]["submitted_answer"] == "可以"
    assert tool_node_inputs[1]["pending_ask"]["status"] == "answered"
    assert isinstance(tool_node_inputs[1]["pending_confirmation"], PendingConfirmation)
    assert set(tool_node_inputs[1]["pending_confirmation"].allowed_tool_names) == {
        "create_task",
        "set_reminder",
    }
    assert tool_node_inputs[1]["pending_confirmation_answer"] == "可以"
    assert tool_node_inputs[1]["tool_history"] == ["ask_user"]
    assert isinstance(tool_node_outputs[1]["db_write_plan"], DBWritePlan)
    assert tool_node_outputs[1]["db_write_plan"].tool_name == "create_task"
    assert (
        tool_node_outputs[1]["db_write_plan"].confirmation_id
        == tool_node_outputs[1]["pending_confirmation"].confirmation_id
    )
    assert isinstance(tool_node_outputs[2]["db_write_plan"], DBWritePlan)
    assert tool_node_outputs[2]["db_write_plan"].tool_name == "set_reminder"
    assert (
        tool_node_outputs[2]["db_write_plan"].confirmation_id
        == tool_node_outputs[2]["pending_confirmation"].confirmation_id
    )
    assert len(tasks) == 1
    assert tasks[0].title == "做饭"
    assert len(reminders) == 1
    assert reminders[0].target_id == tasks[0].id
    assert reminders[0].advance_minutes == 0


@pytest.mark.asyncio
async def test_langgraph_native_study_plan_confirmed_write_does_not_delegate(setup_db):
    from app.agent import langgraph_loop as langgraph_runtime

    observed_plan_states: list[dict] = []
    original_plan_step = langgraph_runtime.run_langgraph_plan_review_write_step
    generated_tasks = [
        {
            "title": "大学英语3复习 - Unit 1",
            "course_name": "大学英语3",
            "date": "2099-06-08",
            "start_time": "09:00",
            "end_time": "10:00",
            "description": "复习 Unit 1 重点。",
        }
    ]
    llm_call_count = 0

    async def fake_generate_study_plan(exams, available_slots, strategy, study_context=None):
        return generated_tasks

    def mock_chat_completion_stream(client, messages, tools=None, tool_choice=None):
        nonlocal llm_call_count
        llm_call_count += 1

        if llm_call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "slots_1",
                            "type": "function",
                            "function": {
                                "name": "get_free_slots",
                                "arguments": json.dumps(
                                    {
                                        "start_date": "2099-06-08",
                                        "end_date": "2099-06-10",
                                        "min_duration_minutes": 60,
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 2:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "plan_1",
                            "type": "function",
                            "function": {
                                "name": "create_study_plan",
                                "arguments": json.dumps(
                                    {
                                        "exams": [{"course_name": "大学英语3", "exam_date": "2099-06-11"}],
                                        "available_slots": {"slots": []},
                                        "study_context": {"raw_notes": "按默认", "using_defaults": True},
                                        "strategy": "balanced",
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(response={"role": "assistant", "content": "done"})

    prompt = "下周四有大学英语3考试，帮我做复习计划"
    state = await prepare_langgraph_state(prompt)
    async def spy_plan_step(state, runtime, *, node_name):
        next_state = await original_plan_step(state, runtime, node_name=node_name)
        observed_plan_states.append(dict(next_state.get("plan_workflow") or {}))
        return next_state

    assert_native_action_graph(state, "study_plan")
    assert "plan_generate" in state["graph_nodes"]
    assert "plan_review_write" in state["graph_nodes"]
    assert "confirmed_write" in state["graph_nodes"]

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.generate_study_plan", side_effect=fake_generate_study_plan),
        patch("app.agent.langgraph_loop.run_langgraph_plan_review_write_step", side_effect=spy_plan_step),
        patch(
            "app.agent.loop._run_confirmed_study_plan_write",
            side_effect=AssertionError("Study plan writeback should be driven by LangGraph plan workflow"),
        ),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Study plan action route should not delegate to run_agent_loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-lg-study-plan", username="lg-study-plan", hashed_password="x")
            db.add(user)
            await db.commit()

            events = await collect_events(
                run_langgraph_agent_loop(prompt, user, "session-lg-study-plan", db, AsyncMock()),
                answers=["确认"],
            )

            task_result = await db.execute(select(Task).where(Task.user_id == user.id))
            tasks = list(task_result.scalars().all())

    assert [event["name"] for event in events if event["type"] == "tool_call"] == [
        "rag_retrieve_study_materials",
        "get_free_slots",
        "create_study_plan",
        "create_task",
    ]
    assert events[-1]["type"] == "done"
    event_graph_nodes = graph_nodes_from_tool_results(events)
    assert "plan_generate" in event_graph_nodes
    assert "plan_review_write" in event_graph_nodes
    assert "confirmed_write" in event_graph_nodes
    assert any(state.get("node") == "plan_review_write" and state.get("pending_confirmation") for state in observed_plan_states)
    assert sum(1 for state in observed_plan_states if state.get("node") == "confirmed_write") == 1
    assert len(tasks) == 1
    assert tasks[0].title == "大学英语3复习 - Unit 1"


@pytest.mark.asyncio
async def test_langgraph_native_work_plan_confirmed_write_does_not_delegate(setup_db):
    from app.agent import langgraph_loop as langgraph_runtime

    observed_plan_states: list[dict] = []
    original_plan_step = langgraph_runtime.run_langgraph_plan_review_write_step
    generated_tasks = [
        {
            "title": "机器学习报告 - 整理资料",
            "work_item_name": "机器学习报告",
            "date": "2099-06-08",
            "start_time": "09:00",
            "end_time": "10:00",
            "description": "整理要求和资料。",
        },
        {
            "title": "机器学习报告 - 完成初稿",
            "work_item_name": "机器学习报告",
            "date": "2099-06-09",
            "start_time": "14:00",
            "end_time": "15:00",
            "description": "完成报告初稿。",
        },
    ]

    async def fake_generate_work_plan(work_items, available_slots, strategy, work_context=None):
        return generated_tasks

    prompt = "2099-06-12 要交机器学习报告，帮我做作业计划。"
    state = await prepare_langgraph_state(prompt)
    assert_native_action_graph(state, "study_plan")
    assert "plan_generate" in state["graph_nodes"]
    assert "plan_review_write" in state["graph_nodes"]
    assert "confirmed_write" in state["graph_nodes"]

    async def spy_plan_step(state, runtime, *, node_name):
        next_state = await original_plan_step(state, runtime, node_name=node_name)
        observed_plan_states.append(dict(next_state.get("plan_workflow") or {}))
        return next_state

    with (
        patch("app.agent.tool_executor.generate_work_plan", side_effect=fake_generate_work_plan),
        patch("app.agent.langgraph_loop.run_langgraph_plan_review_write_step", side_effect=spy_plan_step),
        patch(
            "app.agent.loop._run_work_plan_shortcut",
            side_effect=AssertionError("Work plan action route should be driven by LangGraph plan workflow"),
        ),
        patch(
            "app.agent.loop._run_confirmed_work_plan_write",
            side_effect=AssertionError("Work plan writeback should be driven by LangGraph plan workflow"),
        ),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Study/work plan action route should not delegate to run_agent_loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-lg-work-plan", username="lg-work-plan", hashed_password="x")
            db.add(user)
            await db.commit()

            events = await collect_events(
                run_langgraph_agent_loop(prompt, user, "session-lg-work-plan", db, AsyncMock()),
                answers=["需要5页PDF，包括实验结果。每天最多2小时。", "确认"],
            )

            task_result = await db.execute(
                select(Task).where(Task.user_id == user.id).order_by(Task.scheduled_date)
            )
            tasks = list(task_result.scalars().all())

    assert "create_work_plan" in [event.get("name") for event in events]
    assert [event["name"] for event in events if event["type"] == "tool_call" and event["name"] == "create_task"] == [
        "create_task",
        "create_task",
    ]
    assert events[-1]["type"] == "done"
    event_graph_nodes = graph_nodes_from_tool_results(events)
    assert "plan_generate" in event_graph_nodes
    assert "plan_review_write" in event_graph_nodes
    assert "confirmed_write" in event_graph_nodes
    assert any(state.get("node") == "plan_review_write" and state.get("pending_confirmation") for state in observed_plan_states)
    assert sum(1 for state in observed_plan_states if state.get("node") == "confirmed_write") == 2
    assert [task.title for task in tasks] == ["机器学习报告 - 整理资料", "机器学习报告 - 完成初稿"]


@pytest.mark.asyncio
async def test_langgraph_native_schedule_import_confirmed_write_does_not_delegate(setup_db):
    prompt_template = "please import this schedule file_id={file_id}"
    from app.agent import langgraph_loop as langgraph_runtime

    observed_schedule_states: list[dict] = []
    original_step = langgraph_runtime.run_langgraph_schedule_import_step

    async def spy_schedule_step(state, runtime, *, node_name):
        next_state = await original_step(state, runtime, node_name=node_name)
        observed_schedule_states.append(dict(next_state.get("schedule_import") or {}))
        return next_state

    with patch(
        "app.agent.langgraph_loop.run_agent_loop",
        side_effect=AssertionError("Schedule import action route should not delegate to run_agent_loop"),
    ), patch(
        "app.agent.loop._run_schedule_import_shortcut",
        side_effect=AssertionError("Schedule import action route should be driven by LangGraph workflow nodes"),
    ), patch(
        "app.agent.loop.execute_tool",
        side_effect=AssertionError("Schedule import LangGraph workflow should not execute tools through legacy loop dispatcher"),
    ), patch(
        "app.agent.langgraph_loop.run_langgraph_schedule_import_step",
        side_effect=spy_schedule_step,
    ):
        async with TestSession() as db:
            user = User(
                id="user-lg-schedule",
                username="lg-schedule",
                hashed_password="x",
                current_semester_start=date(2026, 3, 2),
                preferences={"current_term_total_weeks": 18},
            )
            db.add(user)
            await db.commit()
            file_id = store_schedule_upload(
                user_id=user.id,
                kind="spreadsheet",
                courses=[
                    {
                        "name": "LangGraph Native",
                        "weekday": 2,
                        "start_time": "08:30",
                        "end_time": "10:05",
                        "week_start": 1,
                        "week_end": 18,
                        "week_pattern": "all",
                        "week_text": "第1-18周",
                    }
                ],
            )
            prompt = prompt_template.format(file_id=file_id)
            state = await prepare_langgraph_state(prompt)
            assert_native_action_graph(state, "schedule_import")
            assert "schedule_parse" in state["graph_nodes"]
            assert "ask_user_pause" in state["graph_nodes"]
            assert "confirmed_write" in state["graph_nodes"]

            events = await collect_events(
                run_langgraph_agent_loop(prompt, user, "session-lg-schedule", db, AsyncMock()),
                answers=["确认"],
            )

            course_result = await db.execute(select(Course).where(Course.user_id == user.id))
            courses = list(course_result.scalars().all())

    assert [event["name"] for event in events if event["type"] == "tool_call"] == [
        "parse_schedule",
        "bulk_import_courses",
    ]
    assert events[-1]["type"] == "done"
    event_graph_nodes = graph_nodes_from_tool_results(events)
    assert "schedule_parse" in event_graph_nodes
    assert "ask_user_pause" in event_graph_nodes
    assert "confirmed_write" in event_graph_nodes
    assert [state.get("node") for state in observed_schedule_states] == [
        "schedule_parse",
        "ask_user_pause",
        "confirmed_write",
    ]
    assert observed_schedule_states[0]["current_result"]["status"] == "ready"
    assert isinstance(observed_schedule_states[1]["pending_confirmation"], PendingConfirmation)
    assert isinstance(observed_schedule_states[1]["db_write_plan"], DBWritePlan)
    assert observed_schedule_states[2]["confirmed_result"]["status"] == "imported"
    assert len(courses) == 1
    assert courses[0].name == "LangGraph Native"


@pytest.mark.asyncio
async def test_langgraph_native_course_maintenance_confirmed_write_does_not_delegate(setup_db):
    from app.agent import langgraph_loop as langgraph_runtime

    observed_course_states: list[dict] = []
    original_course_step = langgraph_runtime.run_langgraph_course_maintenance_step

    async def spy_course_step(state, runtime, *, node_name):
        next_state = await original_course_step(state, runtime, node_name=node_name)
        observed_course_states.append(dict(next_state.get("course_maintenance") or {}))
        return next_state
    prompt = "把自然语言处理课程改名为 NLP"
    state = await prepare_langgraph_state(prompt)
    assert_native_action_graph(state, "course_maintenance")
    assert "course_disambiguate" in state["graph_nodes"]
    assert "ask_user_pause" in state["graph_nodes"]
    assert "confirmed_write" in state["graph_nodes"]

    with patch(
        "app.agent.langgraph_loop.run_agent_loop",
        side_effect=AssertionError("Course maintenance action route should not delegate to run_agent_loop"),
    ), patch(
        "app.agent.loop._run_course_merge_shortcut",
        side_effect=AssertionError("Course maintenance should be driven by LangGraph workflow nodes"),
    ), patch(
        "app.agent.langgraph_loop.run_langgraph_course_maintenance_step",
        side_effect=spy_course_step,
    ):
        async with TestSession() as db:
            user = User(id="user-lg-course", username="lg-course", hashed_password="x")
            db.add(user)
            db.add(
                Course(
                    user_id=user.id,
                    name="自然语言处理",
                    weekday=1,
                    start_time="08:30",
                    end_time="10:05",
                    week_start=1,
                    week_end=18,
                    week_pattern="all",
                )
            )
            await db.commit()

            events = await collect_events(
                run_langgraph_agent_loop(prompt, user, "session-lg-course", db, AsyncMock()),
                answers=["确认"],
            )

            course_result = await db.execute(select(Course).where(Course.user_id == user.id))
            courses = list(course_result.scalars().all())

    assert [event["name"] for event in events if event["type"] == "tool_call"] == [
        "list_courses",
        "update_course",
    ]
    assert events[-1]["type"] == "done"
    event_graph_nodes = graph_nodes_from_tool_results(events)
    assert "course_disambiguate" in event_graph_nodes
    assert "ask_user_pause" in event_graph_nodes
    assert "confirmed_write" in event_graph_nodes
    assert [course_state.get("node") for course_state in observed_course_states] == [
        "course_disambiguate",
        "ask_user_pause",
        "confirmed_write",
    ]
    assert observed_course_states[0]["current_result"]["courses"]
    assert observed_course_states[0]["actions"][0]["action"] == "update"
    assert isinstance(observed_course_states[1]["pending_confirmation"], PendingConfirmation)
    assert isinstance(observed_course_states[1]["db_write_plan"], DBWritePlan)
    assert observed_course_states[1]["db_write_plan"].tool_name == "update_course"
    assert observed_course_states[2]["confirmed_result"]["status"] == "updated"
    assert len(courses) == 1
    assert courses[0].name == "NLP"


@pytest.mark.asyncio
async def test_langgraph_native_course_maintenance_cancel_does_not_write(setup_db):
    from app.agent import langgraph_loop as langgraph_runtime

    prompt = "把课程 Course Cancel 改名为 Course Written"
    observed_course_states: list[dict] = []
    original_course_step = langgraph_runtime.run_langgraph_course_maintenance_step

    async def spy_course_step(state, runtime, *, node_name):
        next_state = await original_course_step(state, runtime, node_name=node_name)
        observed_course_states.append(dict(next_state.get("course_maintenance") or {}))
        return next_state

    with patch(
        "app.agent.langgraph_loop.run_agent_loop",
        side_effect=AssertionError("Course maintenance action route should not delegate to run_agent_loop"),
    ), patch(
        "app.agent.loop._run_course_merge_shortcut",
        side_effect=AssertionError("Course maintenance should be driven by LangGraph workflow nodes"),
    ), patch(
        "app.agent.langgraph_loop.run_langgraph_course_maintenance_step",
        side_effect=spy_course_step,
    ):
        async with TestSession() as db:
            user = User(id="user-lg-course-cancel", username="lg-course-cancel", hashed_password="x")
            db.add(user)
            db.add(
                Course(
                    user_id=user.id,
                    name="Course Cancel",
                    weekday=1,
                    start_time="08:30",
                    end_time="10:05",
                    week_start=1,
                    week_end=18,
                    week_pattern="all",
                )
            )
            await db.commit()

            events = await collect_events(
                run_langgraph_agent_loop(prompt, user, "session-lg-course-cancel", db, AsyncMock()),
                answers=["取消"],
            )

            course_result = await db.execute(select(Course).where(Course.user_id == user.id))
            courses = list(course_result.scalars().all())

    assert [event["name"] for event in events if event["type"] == "tool_call"] == ["list_courses"]
    assert [course_state.get("node") for course_state in observed_course_states] == [
        "course_disambiguate",
        "ask_user_pause",
    ]
    assert isinstance(observed_course_states[1]["pending_confirmation"], PendingConfirmation)
    assert isinstance(observed_course_states[1]["db_write_plan"], DBWritePlan)
    assert len(courses) == 1
    assert courses[0].name == "Course Cancel"
