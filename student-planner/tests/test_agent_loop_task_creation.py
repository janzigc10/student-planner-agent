from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.loop import run_agent_loop
from app.models.agent_log import AgentLog
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from tests.conftest import TestSession


def stream_response_chunks(*, response: dict):
    async def _generator():
        yield {"type": "response", "response": response}

    return _generator()


@pytest.mark.asyncio
async def test_agent_loop_can_create_task_then_set_reminder(setup_db):
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
                                "arguments": '{"question":"确认创建任务：做饭，2026-05-02 17:00-17:30，并在17:00提醒。","type":"confirm"}',
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
                                "arguments": '{"title":"做饭","scheduled_date":"2026-05-02","start_time":"17:00","end_time":"17:30"}',
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 3:
            create_task_tool_messages = [
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "tool"
            ]
            assert any('"status": "created"' in content for content in create_task_tool_messages)
            task_id = next(
                content.split('"id": "')[1].split('"', 1)[0]
                for content in create_task_tool_messages
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
                                "arguments": f'{{"target_type":"task","target_id":"{task_id}","advance_minutes":0}}',
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(
            response={"role": "assistant", "content": "已经帮你创建做饭任务，并设置 17:00 准点提醒。"}
        )

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="user-agent-task-1", username="agent-task-user", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("17.00提醒我去做饭", user, "session-task-create-1", db, mock_client)

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("可以")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            assert any(event["type"] == "tool_call" and event["name"] == "create_task" for event in events)
            assert any(event["type"] == "tool_call" and event["name"] == "set_reminder" for event in events)
            assert any(event["type"] == "text" and "创建做饭任务" in event["content"] for event in events)
            assert events[-1]["type"] == "done"

            task_result = await db.execute(select(Task).where(Task.user_id == "user-agent-task-1"))
            tasks = list(task_result.scalars().all())
            assert len(tasks) == 1
            assert tasks[0].title == "做饭"
            assert tasks[0].scheduled_date == "2026-05-02"
            assert tasks[0].start_time == "17:00"

            reminder_result = await db.execute(select(Reminder).where(Reminder.user_id == "user-agent-task-1"))
            reminders = list(reminder_result.scalars().all())
            assert len(reminders) == 1
            assert reminders[0].target_type == "task"
            assert reminders[0].advance_minutes == 0


@pytest.mark.asyncio
async def test_agent_loop_can_update_task_time_and_reminder_together(setup_db):
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
                            "id": "ask_update_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question":"确认把 review probability 改到 2026-05-03 15:00-16:00，并提前 30 分钟提醒吗？","type":"confirm"}',
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
                            "id": "update_1",
                            "type": "function",
                            "function": {
                                "name": "update_task",
                                "arguments": (
                                    '{"task_id":"task-agent-update-1",'
                                    '"scheduled_date":"2026-05-03",'
                                    '"start_time":"15:00",'
                                    '"end_time":"16:00",'
                                    '"reminder_advance_minutes":30}'
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(
            response={"role": "assistant", "content": "已更新任务时间和提醒。"}
        )

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.schedule_reminder_job") as mock_schedule,
    ):
        async with TestSession() as db:
            user = User(id="user-agent-task-2", username="agent-task-user-2", hashed_password="x")
            task = Task(
                id="task-agent-update-1",
                user_id="user-agent-task-2",
                title="review probability",
                scheduled_date="2026-05-02",
                start_time="10:00",
                end_time="11:00",
                status="pending",
            )
            reminder = Reminder(
                user_id="user-agent-task-2",
                target_type="task",
                target_id="task-agent-update-1",
                remind_at="2026-05-02T09:45:00",
                advance_minutes=15,
            )
            db.add_all([user, task, reminder])
            await db.commit()

            events = []
            generator = run_agent_loop(
                "改到明天下午3点到4点，提醒提前30分钟",
                user,
                "session-task-update-1",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("可以")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            assert any(event["type"] == "tool_call" and event["name"] == "update_task" for event in events)
            assert any(event["type"] == "text" and "已更新任务时间和提醒" in event["content"] for event in events)
            assert events[-1]["type"] == "done"
            mock_schedule.assert_called_once()

            task_result = await db.execute(select(Task).where(Task.id == "task-agent-update-1"))
            updated_task = task_result.scalar_one()
            assert updated_task.scheduled_date == "2026-05-03"
            assert updated_task.start_time == "15:00"
            assert updated_task.end_time == "16:00"

            reminder_result = await db.execute(
                select(Reminder).where(Reminder.user_id == "user-agent-task-2")
            )
            updated_reminder = reminder_result.scalar_one()
            assert updated_reminder.target_id == "task-agent-update-1"
            assert updated_reminder.advance_minutes == 30
            assert updated_reminder.remind_at == "2026-05-03T14:30:00"


@pytest.mark.asyncio
async def test_agent_loop_fills_missing_reminder_minutes_before_update_task(setup_db):
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
                            "id": "ask_update_missing_reminder",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question":"确认把复习线性代数改到 2026-06-01 16:00-17:00，并提前 15 分钟提醒吗？","type":"confirm"}',
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
                            "id": "update_missing_reminder",
                            "type": "function",
                            "function": {
                                "name": "update_task",
                                "arguments": (
                                    '{"task_id":"task-agent-update-missing-reminder",'
                                    '"start_time":"16:00",'
                                    '"end_time":"17:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(
            response={"role": "assistant", "content": "已更新任务时间和提前15分钟提醒。"}
        )

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.schedule_reminder_job") as mock_schedule,
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-task-missing-reminder",
                username="agent-task-missing-reminder",
                hashed_password="x",
            )
            task = Task(
                id="task-agent-update-missing-reminder",
                user_id="user-agent-task-missing-reminder",
                title="复习线性代数",
                scheduled_date="2026-06-01",
                start_time="15:00",
                end_time="16:00",
                status="pending",
            )
            reminder = Reminder(
                user_id="user-agent-task-missing-reminder",
                target_type="task",
                target_id="task-agent-update-missing-reminder",
                remind_at="2026-06-01T14:30:00",
                advance_minutes=30,
            )
            db.add_all([user, task, reminder])
            await db.commit()

            events = []
            generator = run_agent_loop(
                "把刚才的复习线性代数任务改到明天下午4点到5点，提前15分钟提醒",
                user,
                "session-task-update-missing-reminder",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            update_events = [
                event
                for event in events
                if event["type"] == "tool_call" and event["name"] == "update_task"
            ]
            assert update_events
            assert update_events[0]["args"]["reminder_advance_minutes"] == 15
            mock_schedule.assert_called_once()

            task_result = await db.execute(
                select(Task).where(Task.id == "task-agent-update-missing-reminder")
            )
            updated_task = task_result.scalar_one()
            assert updated_task.start_time == "16:00"
            assert updated_task.end_time == "17:00"

            reminder_result = await db.execute(
                select(Reminder).where(Reminder.user_id == "user-agent-task-missing-reminder")
            )
            updated_reminder = reminder_result.scalar_one()
            assert updated_reminder.target_id == "task-agent-update-missing-reminder"
            assert updated_reminder.advance_minutes == 15
            assert updated_reminder.remind_at == "2026-06-01T15:45:00"


@pytest.mark.asyncio
async def test_agent_loop_blocks_create_task_for_update_intent_then_updates(setup_db):
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
                            "id": "ask_update_guard",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question":"确认把 linear algebra review 改到 2026-07-21 16:00-17:00，并提前 15 分钟提醒吗？","type":"confirm"}',
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
                            "id": "wrong_create_for_update",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": (
                                    '{"title":"linear algebra review",'
                                    '"scheduled_date":"2026-07-21",'
                                    '"start_time":"16:00",'
                                    '"end_time":"17:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 3:
            tool_errors = [
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "tool"
            ]
            assert any("update an existing task" in content for content in tool_errors)
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "guarded_update",
                            "type": "function",
                            "function": {
                                "name": "update_task",
                                "arguments": (
                                    '{"task_id":"task-agent-update-guard",'
                                    '"scheduled_date":"2026-07-21",'
                                    '"start_time":"16:00",'
                                    '"end_time":"17:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(
            response={"role": "assistant", "content": "已更新任务时间和提前15分钟提醒。"}
        )

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.schedule_reminder_job") as mock_schedule,
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-task-update-guard",
                username="agent-task-update-guard",
                hashed_password="x",
            )
            task = Task(
                id="task-agent-update-guard",
                user_id="user-agent-task-update-guard",
                title="linear algebra review",
                scheduled_date="2026-07-20",
                start_time="15:00",
                end_time="16:00",
                status="pending",
            )
            reminder = Reminder(
                user_id="user-agent-task-update-guard",
                target_type="task",
                target_id="task-agent-update-guard",
                remind_at="2026-07-20T14:30:00",
                advance_minutes=30,
            )
            db.add_all([user, task, reminder])
            await db.commit()

            events = []
            generator = run_agent_loop(
                "把已有任务 linear algebra review 改到 2026-07-21 16:00-17:00，提前15分钟提醒",
                user,
                "session-task-update-guard",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            assert not any(
                event["type"] == "tool_call" and event["name"] == "create_task"
                for event in events
            )
            update_events = [
                event
                for event in events
                if event["type"] == "tool_call" and event["name"] == "update_task"
            ]
            assert update_events
            assert update_events[0]["args"]["reminder_advance_minutes"] == 15
            mock_schedule.assert_called_once()

            task_result = await db.execute(
                select(Task).where(Task.user_id == "user-agent-task-update-guard")
            )
            tasks = list(task_result.scalars().all())
            assert len(tasks) == 1
            assert tasks[0].id == "task-agent-update-guard"
            assert tasks[0].scheduled_date == "2026-07-21"
            assert tasks[0].start_time == "16:00"
            assert tasks[0].end_time == "17:00"

            reminder_result = await db.execute(
                select(Reminder).where(Reminder.user_id == "user-agent-task-update-guard")
            )
            reminders = list(reminder_result.scalars().all())
            assert len(reminders) == 1
            assert reminders[0].advance_minutes == 15
            assert reminders[0].remind_at == "2026-07-21T15:45:00"


@pytest.mark.asyncio
async def test_agent_loop_removes_task_reminder_for_explicit_cancel_intent(setup_db):
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
                            "id": "ask_cancel_reminder",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": (
                                    '{"question":"Confirm updating review task to '
                                    '2026-08-01 16:00-17:00 without a reminder?",'
                                    '"type":"confirm"}'
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
                            "id": "update_cancel_reminder",
                            "type": "function",
                            "function": {
                                "name": "update_task",
                                "arguments": (
                                    '{"task_id":"task-agent-cancel-reminder",'
                                    '"scheduled_date":"2026-08-01",'
                                    '"start_time":"16:00",'
                                    '"end_time":"17:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(response={"role": "assistant", "content": "done"})

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.cancel_reminder_job") as mock_cancel,
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-cancel-reminder",
                username="agent-cancel-reminder",
                hashed_password="x",
            )
            task = Task(
                id="task-agent-cancel-reminder",
                user_id="user-agent-cancel-reminder",
                title="review",
                scheduled_date="2026-07-31",
                start_time="15:00",
                end_time="16:00",
                status="pending",
            )
            reminder = Reminder(
                id="reminder-agent-cancel",
                user_id="user-agent-cancel-reminder",
                target_type="task",
                target_id="task-agent-cancel-reminder",
                remind_at="2026-07-31T14:45:00",
                advance_minutes=15,
            )
            db.add_all([user, task, reminder])
            await db.commit()

            events = []
            generator = run_agent_loop(
                (
                    "\u628a\u521a\u624d\u7684review\u4efb\u52a1\u6539\u5230"
                    "2026-08-01 16:00-17:00\uff0c\u4e0d\u63d0\u9192"
                ),
                user,
                "session-task-cancel-reminder",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend(None)
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            update_events = [
                event
                for event in events
                if event["type"] == "tool_call" and event["name"] == "update_task"
            ]
            assert update_events
            assert "reminder_advance_minutes" in update_events[0]["args"]
            assert update_events[0]["args"]["reminder_advance_minutes"] is None
            mock_cancel.assert_called_once_with("reminder-agent-cancel")

            task_result = await db.execute(select(Task).where(Task.id == "task-agent-cancel-reminder"))
            updated_task = task_result.scalar_one()
            assert updated_task.scheduled_date == "2026-08-01"
            assert updated_task.start_time == "16:00"
            assert updated_task.end_time == "17:00"

            reminder_result = await db.execute(
                select(Reminder).where(Reminder.user_id == "user-agent-cancel-reminder")
            )
            reminders = list(reminder_result.scalars().all())
            assert reminders == []


@pytest.mark.asyncio
async def test_agent_loop_blocks_missing_required_tool_args_then_recovers(setup_db):
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
                            "id": "bad_create_missing_date",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": (
                                    '{"title":"review chemistry",'
                                    '"start_time":"16:00",'
                                    '"end_time":"17:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 2:
            tool_errors = [
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "tool"
            ]
            assert any("missing required argument" in content for content in tool_errors)
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "ask_missing_date",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question":"Which date should I use?","type":"review"}',
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 3:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "good_create_after_missing_date",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": (
                                    '{"title":"review chemistry",'
                                    '"scheduled_date":"2026-08-02",'
                                    '"start_time":"16:00",'
                                    '"end_time":"17:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(response={"role": "assistant", "content": "done"})

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(
                id="user-agent-missing-required",
                username="agent-missing-required",
                hashed_password="x",
            )
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop(
                "create a chemistry review task tomorrow from 16:00 to 17:00",
                user,
                "session-task-missing-required",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("2026-08-02")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            create_events = [
                event
                for event in events
                if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert len(create_events) == 1
            assert create_events[0]["args"]["scheduled_date"] == "2026-08-02"

            task_result = await db.execute(select(Task).where(Task.user_id == "user-agent-missing-required"))
            tasks = list(task_result.scalars().all())
            assert len(tasks) == 1
            assert tasks[0].title == "review chemistry"
            assert tasks[0].scheduled_date == "2026-08-02"


@pytest.mark.asyncio
async def test_agent_loop_converts_plain_text_update_confirmation_to_ask_user(setup_db):
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
                            "id": "list_tasks_for_plain_confirm",
                            "type": "function",
                            "function": {"name": "list_tasks", "arguments": "{}"},
                        }
                    ],
                }
            )

        if llm_call_count == 2:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": "找到复习线性代数任务。你确认要改到 2026-07-27 16:00-17:00，并提前15分钟提醒吗？",
                }
            )

        if llm_call_count == 3:
            tool_messages = [
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "tool"
            ]
            assert any("user_response" in content and "确认" in content for content in tool_messages)
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "update_after_plain_confirm",
                            "type": "function",
                            "function": {
                                "name": "update_task",
                                "arguments": (
                                    '{"task_id":"task-plain-confirm-update",'
                                    '"scheduled_date":"2026-07-27",'
                                    '"start_time":"16:00",'
                                    '"end_time":"17:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(response={"role": "assistant", "content": "已更新。"})

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.schedule_reminder_job") as mock_schedule,
    ):
        async with TestSession() as db:
            user = User(
                id="user-plain-confirm-update",
                username="plain-confirm-update",
                hashed_password="x",
            )
            task = Task(
                id="task-plain-confirm-update",
                user_id="user-plain-confirm-update",
                title="复习线性代数",
                scheduled_date="2026-07-26",
                start_time="15:00",
                end_time="16:00",
                status="pending",
            )
            reminder = Reminder(
                user_id="user-plain-confirm-update",
                target_type="task",
                target_id="task-plain-confirm-update",
                remind_at="2026-07-26T14:30:00",
                advance_minutes=30,
            )
            db.add_all([user, task, reminder])
            await db.commit()

            events = []
            generator = run_agent_loop(
                "把刚才的复习线性代数任务改到2026-07-27 16:00-17:00，提前15分钟提醒",
                user,
                "session-plain-confirm-update",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            assert not any(
                event["type"] == "text" and "你确认要改到" in event["content"]
                for event in events
            )
            assert any(event["type"] == "ask_user" for event in events)
            update_events = [
                event
                for event in events
                if event["type"] == "tool_call" and event["name"] == "update_task"
            ]
            assert update_events
            assert update_events[0]["args"]["reminder_advance_minutes"] == 15
            mock_schedule.assert_called_once()

            task_result = await db.execute(select(Task).where(Task.id == "task-plain-confirm-update"))
            updated_task = task_result.scalar_one()
            assert updated_task.scheduled_date == "2026-07-27"
            assert updated_task.start_time == "16:00"
            assert updated_task.end_time == "17:00"

            reminder_result = await db.execute(
                select(Reminder).where(Reminder.user_id == "user-plain-confirm-update")
            )
            updated_reminder = reminder_result.scalar_one()
            assert updated_reminder.advance_minutes == 15
            assert updated_reminder.remind_at == "2026-07-27T15:45:00"


@pytest.mark.asyncio
async def test_agent_loop_converts_plain_text_missing_task_info_to_ask_user(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0

    def mock_chat_completion_stream(client, messages, tools=None, tool_choice=None):
        nonlocal llm_call_count
        llm_call_count += 1

        if llm_call_count == 1:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": "请告诉我哪天、几点到几点复习英语，以及是否需要提前提醒。",
                }
            )

        if llm_call_count == 2:
            tool_messages = [
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "tool"
            ]
            assert any("user_response" in content and "2026-08-02" in content for content in tool_messages)
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "create_after_plain_missing_task_info",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": (
                                    '{"title":"复习英语",'
                                    '"scheduled_date":"2026-08-02",'
                                    '"start_time":"19:00",'
                                    '"end_time":"20:00"}'
                                ),
                            },
                        }
                    ],
                }
            )

        return stream_response_chunks(response={"role": "assistant", "content": "已创建。"})

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.schedule_reminder_job") as mock_schedule,
    ):
        async with TestSession() as db:
            user = User(
                id="user-plain-missing-task-info",
                username="plain-missing-task-info",
                hashed_password="x",
            )
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop(
                "提醒我复习英语",
                user,
                "session-plain-missing-task-info",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("2026-08-02 19:00-20:00，提前15分钟提醒")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            assert not any(
                event["type"] == "text" and "请告诉我哪天" in event["content"]
                for event in events
            )
            assert any(event["type"] == "ask_user" for event in events)
            create_events = [
                event
                for event in events
                if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert create_events
            assert create_events[0]["args"]["reminder_advance_minutes"] == 15
            mock_schedule.assert_called_once()

            task_result = await db.execute(select(Task).where(Task.user_id == "user-plain-missing-task-info"))
            tasks = list(task_result.scalars().all())
            assert len(tasks) == 1
            assert tasks[0].title == "复习英语"
            assert tasks[0].scheduled_date == "2026-08-02"

            reminder_result = await db.execute(
                select(Reminder).where(Reminder.user_id == "user-plain-missing-task-info")
            )
            reminders = list(reminder_result.scalars().all())
            assert len(reminders) == 1
            assert reminders[0].advance_minutes == 15
            assert reminders[0].remind_at == "2026-08-02T18:45:00"


@pytest.mark.asyncio
async def test_agent_loop_handles_missing_task_create_info_locally(setup_db):
    mock_client = AsyncMock()

    with (
        patch("app.agent.loop.chat_completion_stream") as mock_stream,
        patch("app.agent.tool_executor.schedule_reminder_job") as mock_schedule,
    ):
        async with TestSession() as db:
            user = User(
                id="user-local-missing-task-info",
                username="local-missing-task-info",
                hashed_password="x",
            )
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop(
                "帮我创建一个复习英语的任务。",
                user,
                "session-local-missing-task-info",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user" and "请补充" in event["question"]:
                        event = await generator.asend("2026年7月28日晚上7点到8点复习英语，提前15分钟提醒。")
                    elif event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            mock_stream.assert_not_called()
            create_events = [
                event
                for event in events
                if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert create_events
            assert create_events[0]["args"]["scheduled_date"] == "2026-07-28"
            assert create_events[0]["args"]["start_time"] == "19:00"
            assert create_events[0]["args"]["end_time"] == "20:00"
            assert create_events[0]["args"]["reminder_advance_minutes"] == 15
            mock_schedule.assert_called_once()

            task_result = await db.execute(select(Task).where(Task.user_id == "user-local-missing-task-info"))
            tasks = list(task_result.scalars().all())
            assert len(tasks) == 1
            assert tasks[0].title == "复习英语"

            reminder_result = await db.execute(
                select(Reminder).where(Reminder.user_id == "user-local-missing-task-info")
            )
            reminders = list(reminder_result.scalars().all())
            assert len(reminders) == 1
            assert reminders[0].remind_at == "2026-07-28T18:45:00"


@pytest.mark.asyncio
async def test_agent_loop_writes_confirmed_study_plan_tasks(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0
    generated_tasks = [
        {
            "title": "大学英语3 - 词汇与短语",
            "exam_name": "大学英语3",
            "date": "2026-06-03",
            "start_time": "09:00",
            "end_time": "10:30",
            "description": "复习核心词汇、短语搭配和易错表达。",
        },
        {
            "title": "大学英语3 - 阅读训练",
            "exam_name": "大学英语3",
            "date": "2026-06-04",
            "start_time": "14:00",
            "end_time": "16:00",
            "description": "完成两篇阅读理解并整理错题。",
        },
    ]

    plan_available_slots: list[dict[str, object]] = []
    plan_study_contexts: list[dict[str, object] | None] = []

    async def fake_generate_study_plan(exams, available_slots, strategy, study_context=None):
        plan_available_slots.append(available_slots)
        plan_study_contexts.append(study_context)
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
                            "id": "ask_exam_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question":"确认考试信息：2026-06-11 大学英语3。","type":"confirm"}',
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
                            "id": "free_slots_1",
                            "type": "function",
                            "function": {
                                "name": "get_free_slots",
                                "arguments": '{"start_date":"2026-06-03","end_date":"2026-06-10"}',
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 3:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "study_plan_1",
                            "type": "function",
                            "function": {
                                "name": "create_study_plan",
                                "arguments": (
                                    '{"exams":[{"course_name":"大学英语3","exam_date":"2026-06-11"}],'
                                    '"available_slots":{"total_free_hours":42,"free_slot_count":8},'
                                    '"strategy":"balanced"}'
                                ),
                            },
                        }
                    ],
                }
            )

        raise AssertionError("The loop should not ask the model to continue after confirmed study plan write")

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.generate_study_plan", side_effect=fake_generate_study_plan),
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-study-plan-write",
                username="agent-study-plan-write",
                hashed_password="x",
            )
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop(
                "下周四（2026-06-11）有大学英语3考试，帮我做一个复习计划。",
                user,
                "session-agent-study-plan-write",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user" and "拆得更准" in event["question"]:
                        event = await generator.asend("范围 Unit1-6，听力和写作薄弱，目标80分，每天最多2小时。")
                    elif event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            create_task_calls = [
                event for event in events if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert len(create_task_calls) == 2
            assert not any(event["type"] == "ask_user" and "拆得更准" in event["question"] for event in events)
            assert any(
                event["type"] == "ask_user"
                and isinstance(event.get("data"), dict)
                and event["data"].get("count") == 2
                for event in events
            )
            assert any(event["type"] == "text" and "2 条复习任务写入日程" in event["content"] for event in events)
            assert len(plan_available_slots) == 1
            assert isinstance(plan_available_slots[0].get("slots"), list)
            assert plan_available_slots[0]["slots"][0]["date"] == "2026-06-03"
            assert len(plan_study_contexts) == 1
            assert plan_study_contexts[0] is not None
            assert plan_study_contexts[0]["using_defaults"] is True
            assert plan_study_contexts[0]["raw_notes"] == "按默认"

            task_result = await db.execute(
                select(Task).where(Task.user_id == "user-agent-study-plan-write").order_by(Task.scheduled_date)
            )
            tasks = list(task_result.scalars().all())
            assert [task.title for task in tasks] == ["大学英语3 - 词汇与短语", "大学英语3 - 阅读训练"]
            assert [task.scheduled_date for task in tasks] == ["2026-06-03", "2026-06-04"]
            assert tasks[0].description == "复习核心词汇、短语搭配和易错表达。"

            log_result = await db.execute(
                select(AgentLog.tool_called)
                .where(AgentLog.user_id == "user-agent-study-plan-write")
                .order_by(AgentLog.step)
            )
            tool_names = list(log_result.scalars().all())
            assert tool_names.count("create_study_plan") == 1
            assert tool_names.count("create_task") == 2


@pytest.mark.asyncio
async def test_agent_loop_collects_context_for_detailed_study_plan(setup_db):
    mock_client = AsyncMock()

    async with TestSession() as db:
        user = User(
            id="user-agent-detailed-study-plan",
            username="agent-detailed-study-plan",
            hashed_password="x",
        )
        db.add(user)
        await db.commit()

        generator = run_agent_loop(
            "2026-06-11 有大学英语3考试，帮我做一个详细复习计划。",
            user,
            "session-agent-detailed-study-plan",
            db,
            mock_client,
        )

        event = await generator.__anext__()
        assert event["type"] == "ask_user"
        assert "拆得更准" in event["question"]
        await generator.aclose()


@pytest.mark.asyncio
async def test_agent_loop_writes_confirmed_work_plan_tasks_locally(setup_db):
    mock_client = AsyncMock()
    generated_tasks = [
        {
            "title": "机器学习报告 - 整理要求和资料",
            "work_item_name": "机器学习报告",
            "date": "2099-06-08",
            "start_time": "09:00",
            "end_time": "10:00",
            "description": "确认5页PDF、实验结果和参考文献要求。",
        },
        {
            "title": "机器学习报告 - 完成提纲",
            "work_item_name": "机器学习报告",
            "date": "2099-06-09",
            "start_time": "10:00",
            "end_time": "11:00",
            "description": "列出报告结构和实验结果位置。",
        },
        {
            "title": "机器学习报告 - 完成初稿",
            "work_item_name": "机器学习报告",
            "date": "2099-06-10",
            "start_time": "14:00",
            "end_time": "16:00",
            "description": "完成报告主体初稿。",
        },
    ]
    captured_work_contexts: list[dict[str, object] | None] = []

    async def fake_generate_work_plan(work_items, available_slots, strategy, work_context=None):
        captured_work_contexts.append(work_context)
        return generated_tasks

    with (
        patch("app.agent.loop.chat_completion_stream") as mock_stream,
        patch("app.agent.tool_executor.generate_work_plan", side_effect=fake_generate_work_plan),
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-work-plan-write",
                username="agent-work-plan-write",
                hashed_password="x",
            )
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop(
                "2099-06-12 要交机器学习报告，帮我拆成任务。",
                user,
                "session-agent-work-plan-write",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user" and "拆得更准" in event["question"]:
                        event = await generator.asend("需要5页PDF，包括实验结果和参考文献，每天最多2小时。")
                    elif event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            mock_stream.assert_not_called()
            assert any(event["type"] == "tool_call" and event["name"] == "get_free_slots" for event in events)
            assert any(event["type"] == "tool_call" and event["name"] == "create_work_plan" for event in events)
            create_task_calls = [
                event for event in events if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert len(create_task_calls) == 3
            assert captured_work_contexts[0] is not None
            assert captured_work_contexts[0]["requirements"] == "需要5页PDF，包括实验结果和参考文献，每天最多2小时。"
            assert captured_work_contexts[0]["daily_work_limit_minutes"] == 120
            assert any(event["type"] == "text" and "3 条作业任务写入日程" in event["content"] for event in events)

            task_result = await db.execute(
                select(Task)
                .where(Task.user_id == "user-agent-work-plan-write")
                .order_by(Task.scheduled_date)
            )
            tasks = list(task_result.scalars().all())
            assert [task.title for task in tasks] == [
                "机器学习报告 - 整理要求和资料",
                "机器学习报告 - 完成提纲",
                "机器学习报告 - 完成初稿",
            ]


@pytest.mark.asyncio
async def test_agent_loop_reschedules_confirmed_plan_task_after_time_conflict(setup_db):
    mock_client = AsyncMock()
    generated_tasks = [
        {
            "title": "机器学习报告 - 整理要求和资料",
            "work_item_name": "机器学习报告",
            "date": "2099-06-08",
            "start_time": "09:00",
            "end_time": "10:00",
            "description": "确认报告要求和资料。",
        },
    ]

    async def fake_generate_work_plan(work_items, available_slots, strategy, work_context=None):
        return generated_tasks

    with (
        patch("app.agent.loop.chat_completion_stream") as mock_stream,
        patch("app.agent.tool_executor.generate_work_plan", side_effect=fake_generate_work_plan),
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-work-plan-reschedule",
                username="agent-work-plan-reschedule",
                hashed_password="x",
            )
            blocker = Task(
                id="task-work-plan-conflict",
                user_id="user-agent-work-plan-reschedule",
                title="已有安排",
                scheduled_date="2099-06-08",
                start_time="09:00",
                end_time="10:00",
            )
            db.add_all([user, blocker])
            await db.commit()

            events = []
            generator = run_agent_loop(
                "2099-06-12 要交机器学习报告，帮我拆成任务。",
                user,
                "session-agent-work-plan-reschedule",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user" and "拆得更准" in event["question"]:
                        event = await generator.asend("需要5页PDF，包括实验结果和参考文献，每天最多2小时。")
                    elif event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            mock_stream.assert_not_called()
            assert any(event["type"] == "text" and "自动重排" in event["content"] for event in events)

            create_task_calls = [
                event for event in events if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert len(create_task_calls) == 2
            assert create_task_calls[0]["args"]["start_time"] == "09:00"
            assert create_task_calls[1]["args"]["start_time"] == "10:00"
            assert create_task_calls[1]["args"]["end_time"] == "11:00"
            assert any(
                event["type"] == "tool_call"
                and event["name"] == "get_free_slots"
                and event["args"]["start_date"] == "2099-06-08"
                and event["args"]["end_date"] == "2099-06-08"
                and event["args"]["min_duration_minutes"] == 60
                for event in events
            )

            task_result = await db.execute(
                select(Task)
                .where(Task.user_id == "user-agent-work-plan-reschedule")
                .order_by(Task.start_time)
            )
            tasks = list(task_result.scalars().all())
            assert [(task.title, task.start_time, task.end_time) for task in tasks] == [
                ("已有安排", "09:00", "10:00"),
                ("机器学习报告 - 整理要求和资料", "10:00", "11:00"),
            ]

            log_result = await db.execute(
                select(AgentLog.tool_called)
                .where(AgentLog.user_id == "user-agent-work-plan-reschedule")
                .order_by(AgentLog.step)
            )
            tool_names = list(log_result.scalars().all())
            assert tool_names == [
                "get_free_slots",
                "create_work_plan",
                "create_task",
                "get_free_slots",
                "create_task",
            ]


@pytest.mark.asyncio
async def test_agent_loop_reports_unwritten_plan_task_when_conflict_has_no_free_slot(setup_db):
    mock_client = AsyncMock()
    generated_tasks = [
        {
            "title": "机器学习报告 - 整理要求和资料",
            "work_item_name": "机器学习报告",
            "date": "2099-06-08",
            "start_time": "09:00",
            "end_time": "10:00",
            "description": "确认报告要求和资料。",
        },
    ]

    async def fake_generate_work_plan(work_items, available_slots, strategy, work_context=None):
        return generated_tasks

    with (
        patch("app.agent.loop.chat_completion_stream") as mock_stream,
        patch("app.agent.tool_executor.generate_work_plan", side_effect=fake_generate_work_plan),
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-work-plan-no-reschedule-slot",
                username="agent-work-plan-no-reschedule-slot",
                hashed_password="x",
            )
            blocker = Task(
                id="task-work-plan-all-day-conflict",
                user_id="user-agent-work-plan-no-reschedule-slot",
                title="全天已有安排",
                scheduled_date="2099-06-08",
                start_time="08:00",
                end_time="22:00",
            )
            db.add_all([user, blocker])
            await db.commit()

            events = []
            generator = run_agent_loop(
                "2099-06-12 要交机器学习报告，帮我拆成任务。",
                user,
                "session-agent-work-plan-no-reschedule-slot",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user" and "拆得更准" in event["question"]:
                        event = await generator.asend("需要5页PDF，包括实验结果和参考文献，每天最多2小时。")
                    elif event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            mock_stream.assert_not_called()
            assert any(event["type"] == "text" and "暂时没有写入成功" in event["content"] for event in events)
            create_task_calls = [
                event for event in events if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert len(create_task_calls) == 1
            assert any(event["type"] == "tool_call" and event["name"] == "get_free_slots" for event in events)

            task_result = await db.execute(
                select(Task).where(Task.user_id == "user-agent-work-plan-no-reschedule-slot")
            )
            tasks = list(task_result.scalars().all())
            assert len(tasks) == 1
            assert tasks[0].title == "全天已有安排"


@pytest.mark.asyncio
async def test_agent_loop_adjusts_existing_plan_daily_limit_locally(setup_db):
    mock_client = AsyncMock()
    target_date = (date.today() + timedelta(days=1)).isoformat()

    with patch("app.agent.loop.chat_completion_stream") as mock_stream:
        async with TestSession() as db:
            user = User(
                id="user-agent-plan-adjust",
                username="agent-plan-adjust",
                hashed_password="x",
            )
            first_task = Task(
                id="task-plan-adjust-1",
                user_id="user-agent-plan-adjust",
                title="机器学习报告 - 完成初稿",
                scheduled_date=target_date,
                start_time="09:00",
                end_time="11:00",
                status="pending",
            )
            second_task = Task(
                id="task-plan-adjust-2",
                user_id="user-agent-plan-adjust",
                title="机器学习报告 - 修改完善",
                scheduled_date=(date.today() + timedelta(days=2)).isoformat(),
                start_time="14:00",
                end_time="16:00",
                status="pending",
            )
            db.add_all([user, first_task, second_task])
            await db.commit()

            events = []
            generator = run_agent_loop(
                "机器学习报告计划太满了，改成每天最多1小时。",
                user,
                "session-agent-plan-adjust",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            mock_stream.assert_not_called()
            assert any(event["type"] == "tool_call" and event["name"] == "list_tasks" for event in events)
            update_calls = [
                event for event in events if event["type"] == "tool_call" and event["name"] == "update_task"
            ]
            assert len(update_calls) == 2
            assert all(event["args"]["end_time"] in {"10:00", "15:00"} for event in update_calls)

            task_result = await db.execute(
                select(Task)
                .where(Task.user_id == "user-agent-plan-adjust")
                .order_by(Task.scheduled_date)
            )
            tasks = list(task_result.scalars().all())
            assert tasks[0].end_time == "10:00"
            assert tasks[1].end_time == "15:00"

            log_result = await db.execute(
                select(AgentLog.tool_called)
                .where(AgentLog.user_id == "user-agent-plan-adjust")
                .order_by(AgentLog.step)
            )
            tool_names = list(log_result.scalars().all())
            assert tool_names.count("list_tasks") == 1
            assert tool_names.count("update_task") == 2


@pytest.mark.asyncio
async def test_agent_loop_writes_multi_exam_study_plan_tasks(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0
    generated_tasks = [
        {
            "title": "高等数学 - 极限与导数",
            "exam_name": "高等数学",
            "date": "2026-06-08",
            "start_time": "09:00",
            "end_time": "10:00",
            "description": "复习第1-3章基础题。",
        },
        {
            "title": "大学英语3 - Unit1-6 听力",
            "exam_name": "大学英语3",
            "date": "2026-06-09",
            "start_time": "14:00",
            "end_time": "15:00",
            "description": "完成Unit1-6听力专项训练。",
        },
    ]

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
                            "id": "ask_multi_exam",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question":"确认两门考试：2026-06-10 高等数学，2026-06-12 大学英语3。","type":"confirm"}',
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
                            "id": "free_slots_multi_exam",
                            "type": "function",
                            "function": {
                                "name": "get_free_slots",
                                "arguments": '{"start_date":"2026-06-03","end_date":"2026-06-11"}',
                            },
                        }
                    ],
                }
            )

        if llm_call_count == 3:
            return stream_response_chunks(
                response={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "study_plan_multi_exam",
                            "type": "function",
                            "function": {
                                "name": "create_study_plan",
                                "arguments": (
                                    '{"exams":['
                                    '{"course_name":"高等数学","exam_date":"2026-06-10","difficulty":"hard"},'
                                    '{"course_name":"大学英语3","exam_date":"2026-06-12","difficulty":"medium"}'
                                    '],'
                                    '"available_slots":{"slots":[]},'
                                    '"study_context":{"exam_scope":"高数第1-5章；英语Unit1-6","daily_study_limit_minutes":120},'
                                    '"strategy":"balanced"}'
                                ),
                            },
                        }
                    ],
                }
            )

        raise AssertionError("The loop should stop after confirmed multi-exam study plan write")

    with (
        patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream),
        patch("app.agent.tool_executor.generate_study_plan", side_effect=fake_generate_study_plan),
    ):
        async with TestSession() as db:
            user = User(
                id="user-agent-multi-exam",
                username="agent-multi-exam",
                hashed_password="x",
            )
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop(
                "2026-06-10 高等数学考试，范围第1-5章；2026-06-12 大学英语3考试，范围Unit1-6。帮我做复习计划，每天最多2小时。",
                user,
                "session-agent-multi-exam",
                db,
                mock_client,
            )

            event = await generator.__anext__()
            while True:
                events.append(event)
                try:
                    if event["type"] == "ask_user":
                        event = await generator.asend("确认")
                    else:
                        event = await generator.__anext__()
                except StopAsyncIteration:
                    break

            create_task_calls = [
                event for event in events if event["type"] == "tool_call" and event["name"] == "create_task"
            ]
            assert len(create_task_calls) == 2

            task_result = await db.execute(
                select(Task)
                .where(Task.user_id == "user-agent-multi-exam")
                .order_by(Task.scheduled_date)
            )
            tasks = list(task_result.scalars().all())
            assert any("高等数学" in task.title for task in tasks)
            assert any("大学英语3" in task.title for task in tasks)
