from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.loop import run_agent_loop
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
