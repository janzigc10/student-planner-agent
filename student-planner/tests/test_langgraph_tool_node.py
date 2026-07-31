import json

import pytest
from sqlalchemy import select

from app.agent.contracts import PendingConfirmation
from app.agent.langgraph_loop import (
    GraphToolNodeRuntime,
    resume_langgraph_ask_user_state,
    run_langgraph_tool_node,
)
from app.models.agent_log import AgentLog
from app.models.course import Course
from app.models.user import User
from tests.conftest import TestSession


def _tool_call(name: str, args: dict, call_id: str = "call-1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


def _base_state(name: str, args: dict, **overrides) -> dict:
    state = {
        "pending_tool_call": _tool_call(name, args),
        "messages": [],
        "tool_history": [],
        "error_count": {},
        "preflight_reference_texts": [],
        "preflight_user_texts": [],
        "step": 0,
        "events": [],
        "graph_nodes": [],
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_langgraph_tool_node_blocks_unknown_tool_without_execution(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-unknown", username="tool-node-unknown", hashed_password="x")
        db.add(user)
        await db.commit()

        state = await run_langgraph_tool_node(
            _base_state("missing_tool", {}),
            GraphToolNodeRuntime(db=db, user_id=user.id, session_id="session-tool-node-unknown"),
        )

    assert state["events"] == [{"type": "error", "message": "工具 'missing_tool' 不存在。"}]
    assert state["tool_history"] == []
    assert state["error_count"] == {}
    assert state["messages"][0]["role"] == "tool"
    assert "missing_tool" in state["messages"][0]["content"]


@pytest.mark.asyncio
async def test_langgraph_tool_node_blocks_consecutive_ask_user_without_user_visible_error(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-ask", username="tool-node-ask", hashed_password="x")
        db.add(user)
        await db.commit()

        state = await run_langgraph_tool_node(
            _base_state("ask_user", {"question": "确认？"}, tool_history=["ask_user"]),
            GraphToolNodeRuntime(db=db, user_id=user.id, session_id="session-tool-node-ask"),
        )

    assert state["events"] == []
    assert state["tool_history"] == ["ask_user"]
    assert "ask_user" in state["messages"][0]["content"]


@pytest.mark.asyncio
async def test_langgraph_tool_node_records_pending_ask_and_resume_confirmation_state(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-ask-state", username="tool-node-ask-state", hashed_password="x")
        db.add(user)
        await db.commit()

        state = await run_langgraph_tool_node(
            _base_state(
                "ask_user",
                {
                    "question": "Confirm creating Smoke task with a reminder?",
                    "type": "confirm",
                    "data": {
                        "tasks": [
                            {
                                "title": "Smoke task",
                                "scheduled_date": "2099-06-01",
                                "start_time": "15:00",
                                "end_time": "16:00",
                            }
                        ]
                    },
                },
            ),
            GraphToolNodeRuntime(db=db, user_id=user.id, session_id="session-tool-node-ask-state"),
        )

    assert state["pending_ask"]["status"] == "awaiting_answer"
    assert state["pending_ask"]["tool_name"] == "ask_user"
    assert state["pending_ask"]["tool_call_id"] == "call-1"
    assert state["resume_state"] == {
        "status": "awaiting_answer",
        "tool_name": "ask_user",
        "tool_call_id": "call-1",
    }
    assert state["tool_history"] == ["ask_user"]

    resumed = resume_langgraph_ask_user_state(state, user_response="确认")

    assert resumed["submitted_answer"] == "确认"
    assert resumed["pending_ask"]["status"] == "answered"
    assert resumed["pending_ask"]["answer"] == "确认"
    assert isinstance(resumed["pending_confirmation"], PendingConfirmation)
    assert resumed["pending_confirmation"].allowed_tool_names == ("create_task",)
    assert resumed["pending_confirmation_answer"] == "确认"
    assert resumed["resume_state"]["status"] == "answered"
    assert resumed["resume_state"]["submitted_answer"] == "确认"
    assert resumed["tool_history"] == ["ask_user"]
    assert resumed["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": json.dumps({"user_response": "确认"}, ensure_ascii=False),
    }


@pytest.mark.asyncio
async def test_langgraph_tool_node_blocks_max_retry_before_execution(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-retry", username="tool-node-retry", hashed_password="x")
        db.add(user)
        await db.commit()

        state = await run_langgraph_tool_node(
            _base_state("list_courses", {}, error_count={"list_courses": 2}),
            GraphToolNodeRuntime(db=db, user_id=user.id, session_id="session-tool-node-retry"),
        )

    assert state["events"][0]["type"] == "error"
    assert "list_courses" in state["events"][0]["message"]
    assert state["tool_history"] == []
    assert state["error_count"] == {"list_courses": 2}


@pytest.mark.asyncio
async def test_langgraph_tool_node_schema_preflight_blocks_missing_required_arg(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-schema", username="tool-node-schema", hashed_password="x")
        db.add(user)
        await db.commit()

        state = await run_langgraph_tool_node(
            _base_state("create_task", {"title": "review"}),
            GraphToolNodeRuntime(db=db, user_id=user.id, session_id="session-tool-node-schema"),
        )

    assert state["events"] == []
    assert state["tool_history"] == []
    assert "scheduled_date" in state["messages"][0]["content"]


@pytest.mark.asyncio
async def test_langgraph_tool_node_repairs_reminder_slot_and_logs_updated_args(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-preflight", username="tool-node-preflight", hashed_password="x")
        db.add(user)
        await db.commit()
        captured_args = {}

        async def fake_confirmed_executor(tool_name, tool_args):
            captured_args.update(tool_args)
            return {"status": "updated", "args": dict(tool_args)}

        state = await run_langgraph_tool_node(
            _base_state(
                "update_task",
                {"task_id": "task-preflight", "start_time": "16:00", "end_time": "17:00"},
                preflight_reference_texts=[
                    "\u628a\u521a\u624d\u7684\u4efb\u52a1\u6539\u5230\u4e0b\u53484\u70b9\u52305\u70b9\uff0c\u63d0\u524d15\u5206\u949f\u63d0\u9192"
                ],
                preflight_user_texts=[
                    "\u628a\u521a\u624d\u7684\u4efb\u52a1\u6539\u5230\u4e0b\u53484\u70b9\u52305\u70b9\uff0c\u63d0\u524d15\u5206\u949f\u63d0\u9192"
                ],
            ),
            GraphToolNodeRuntime(
                db=db,
                user_id=user.id,
                session_id="session-tool-node-preflight",
                confirmed_write_executor=fake_confirmed_executor,
            ),
        )

        log_result = await db.execute(select(AgentLog).where(AgentLog.session_id == "session-tool-node-preflight"))
        logs = list(log_result.scalars().all())

    assert state["events"][0] == {
        "type": "tool_call",
        "name": "update_task",
        "args": {
            "task_id": "task-preflight",
            "start_time": "16:00",
            "end_time": "17:00",
            "reminder_advance_minutes": 15,
        },
        "graph_node": "task_tool_node",
    }
    assert state["events"][1]["type"] == "tool_result"
    assert state["events"][1]["result"]["status"] == "updated"
    assert captured_args["reminder_advance_minutes"] == 15
    assert state["tool_history"] == ["update_task"]
    assert logs[0].step == 1
    assert logs[0].tool_called == "update_task"
    assert logs[0].tool_args["reminder_advance_minutes"] == 15


@pytest.mark.asyncio
async def test_langgraph_tool_node_records_tool_error_and_retry_state(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-error", username="tool-node-error", hashed_password="x")
        db.add(user)
        await db.commit()
        async def fake_confirmed_executor(tool_name, tool_args):
            return {"error": "Task not found"}

        state = await run_langgraph_tool_node(
            _base_state("update_task", {"task_id": "missing-task", "status": "completed"}),
            GraphToolNodeRuntime(
                db=db,
                user_id=user.id,
                session_id="session-tool-node-error",
                confirmed_write_executor=fake_confirmed_executor,
            ),
        )

    assert [event["type"] for event in state["events"]] == ["tool_call", "tool_result"]
    assert state["events"][1]["result"] == {"error": "Task not found"}
    assert state["error_count"] == {"update_task": 1}
    assert state["tool_history"] == ["update_task"]
    assert state["last_tool_result"] == {"error": "Task not found"}


@pytest.mark.asyncio
async def test_langgraph_tool_node_persists_tool_result_and_agent_log_in_order(setup_db):
    async with TestSession() as db:
        user = User(id="tool-node-log", username="tool-node-log", hashed_password="x")
        db.add(user)
        db.add(
            Course(
                user_id=user.id,
                name="高等数学",
                weekday=1,
                start_time="08:30",
                end_time="10:15",
                week_start=1,
                week_end=18,
                week_pattern="all",
                week_text="第1-18周",
            )
        )
        await db.commit()

        state = await run_langgraph_tool_node(
            _base_state("list_courses", {}),
            GraphToolNodeRuntime(db=db, user_id=user.id, session_id="session-tool-node-log"),
        )

        log_result = await db.execute(
            select(AgentLog).where(AgentLog.session_id == "session-tool-node-log").order_by(AgentLog.step)
        )
        logs = list(log_result.scalars().all())

    assert [event["type"] for event in state["events"]] == ["tool_call", "tool_result"]
    assert state["events"][0]["name"] == "list_courses"
    assert state["events"][1]["result"]["count"] == 1
    assert state["messages"][-1]["role"] == "tool"
    assert state["tool_history"] == ["list_courses"]
    assert state["step"] == 1
    assert logs[0].step == 1
    assert logs[0].tool_called == "list_courses"
    assert logs[0].tool_result["count"] == 1
