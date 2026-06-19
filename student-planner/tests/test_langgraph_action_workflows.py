import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.langgraph_loop import prepare_langgraph_state, run_langgraph_agent_loop
from app.models.course import Course
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services.schedule_upload_cache import store_schedule_upload
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


@pytest.mark.asyncio
async def test_langgraph_native_task_reminder_confirmed_write_does_not_delegate(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0

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

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
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
    assert len(tasks) == 1
    assert tasks[0].title == "做饭"
    assert len(reminders) == 1
    assert reminders[0].target_id == tasks[0].id
    assert reminders[0].advance_minutes == 0


@pytest.mark.asyncio
async def test_langgraph_native_work_plan_confirmed_write_does_not_delegate(setup_db):
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

    with (
        patch("app.agent.tool_executor.generate_work_plan", side_effect=fake_generate_work_plan),
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
    assert [task.title for task in tasks] == ["机器学习报告 - 整理资料", "机器学习报告 - 完成初稿"]


@pytest.mark.asyncio
async def test_langgraph_native_schedule_import_confirmed_write_does_not_delegate(setup_db):
    prompt_template = "please import this schedule file_id={file_id}"

    with patch(
        "app.agent.langgraph_loop.run_agent_loop",
        side_effect=AssertionError("Schedule import action route should not delegate to run_agent_loop"),
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
    assert len(courses) == 1
    assert courses[0].name == "LangGraph Native"


@pytest.mark.asyncio
async def test_langgraph_native_course_maintenance_confirmed_write_does_not_delegate(setup_db):
    prompt = "把自然语言处理课程改名为 NLP"
    state = await prepare_langgraph_state(prompt)
    assert_native_action_graph(state, "course_maintenance")

    with patch(
        "app.agent.langgraph_loop.run_agent_loop",
        side_effect=AssertionError("Course maintenance action route should not delegate to run_agent_loop"),
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
    assert len(courses) == 1
    assert courses[0].name == "NLP"
