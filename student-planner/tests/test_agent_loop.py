from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.loop import run_agent_loop
from app.models.conversation_message import ConversationMessage
from app.models.course import Course
from app.models.user import User
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_simple_text_response(setup_db):
    """LLM returns text without tool calls and loop ends immediately."""
    mock_client = AsyncMock()

    with patch("app.agent.loop.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": "你好！有什么可以帮你的？",
        }

        async with TestSession() as db:
            user = User(id="u1", username="test", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("你好", user, "session-1", db, mock_client)
            async for event in generator:
                events.append(event)

            assert any(event["type"] == "text" for event in events)
            assert any(event["type"] == "done" for event in events)
            text_event = next(event for event in events if event["type"] == "text")
            assert "你好" in text_event["content"]


@pytest.mark.asyncio
async def test_tool_call_then_text(setup_db):
    """LLM calls a tool, gets result, then responds with text."""
    mock_client = AsyncMock()
    call_count = 0

    async def mock_chat_completion(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "list_courses", "arguments": "{}"},
                    }
                ],
            }
        return {"role": "assistant", "content": "你目前没有课程。"}

    with patch("app.agent.loop.chat_completion", side_effect=mock_chat_completion):
        async with TestSession() as db:
            user = User(id="u2", username="test2", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            generator = run_agent_loop("我有什么课", user, "session-2", db, mock_client)
            async for event in generator:
                events.append(event)

            types = [event["type"] for event in events]
            assert "tool_call" in types
            assert "tool_result" in types
            assert "text" in types
            assert "done" in types


@pytest.mark.asyncio
async def test_ask_user_event_preserves_event_type(setup_db):
    """ask_user events expose event type separately from confirm/select/review mode."""
    mock_client = AsyncMock()
    call_count = 0

    async def mock_chat_completion(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "ask_user",
                            "arguments": '{"question": "确认吗？", "type": "confirm", "options": ["确认", "取消"]}',
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "继续执行。"}

    with patch("app.agent.loop.chat_completion", side_effect=mock_chat_completion):
        async with TestSession() as db:
            user = User(id="u3", username="test3", hashed_password="x")
            db.add(user)
            await db.commit()

            generator = run_agent_loop("帮我安排", user, "session-3", db, mock_client)
            event = await generator.__anext__()
            assert event["type"] == "tool_call"

            ask_event = await generator.__anext__()
            assert ask_event["type"] == "ask_user"
            assert ask_event["ask_type"] == "confirm"


@pytest.mark.asyncio
async def test_ask_user_without_options_or_data_defaults_to_review(setup_db):
    """ask_user confirm without options/data should degrade to free-text review mode."""
    mock_client = AsyncMock()
    call_count = 0

    async def mock_chat_completion(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "ask_user",
                            "arguments": '{"question": "请补充节次时间", "type": "confirm"}',
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "收到"}

    with patch("app.agent.loop.chat_completion", side_effect=mock_chat_completion):
        async with TestSession() as db:
            user = User(id="u4", username="test4", hashed_password="x")
            db.add(user)
            await db.commit()

            generator = run_agent_loop("帮我安排", user, "session-4", db, mock_client)
            event = await generator.__anext__()
            assert event["type"] == "tool_call"

            ask_event = await generator.__anext__()
            assert ask_event["type"] == "ask_user"
            assert ask_event["ask_type"] == "review"


@pytest.mark.asyncio
async def test_continue_message_can_reuse_persisted_list_course_summary(setup_db):
    mock_client = AsyncMock()
    llm_call_count = 0
    session_id = "session-delete-continue"
    target_course_id = "course-target"

    async def mock_chat_completion(client, messages, tools=None):
        nonlocal llm_call_count
        llm_call_count += 1
        if llm_call_count == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_list",
                        "type": "function",
                        "function": {"name": "list_courses", "arguments": "{}"},
                    }
                ],
            }
        if llm_call_count == 2:
            return {"role": "assistant", "content": "已经找到了候选课程。"}
        if llm_call_count == 3:
            summaries = [
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "assistant"
                and str(message.get("content") or "").startswith("[TOOL_SUMMARY:list_courses:v1] ")
            ]
            assert summaries, "第二轮没有看到 list_courses 摘要"
            latest_summary = summaries[-1]
            assert target_course_id in latest_summary
            assert "会展-305" in latest_summary
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_delete",
                        "type": "function",
                        "function": {
                            "name": "delete_course",
                            "arguments": '{"course_id": "course-target"}',
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "已删除会展-305的自然语言处理。"}

    with patch("app.agent.loop.chat_completion", side_effect=mock_chat_completion):
        async with TestSession() as db:
            user = User(id="u6", username="test6", hashed_password="x")
            db.add(user)
            db.add_all(
                [
                    Course(
                        id=target_course_id,
                        user_id="u6",
                        name="自然语言处理",
                        location="会展-305",
                        weekday=3,
                        start_time="08:30",
                        end_time="10:05",
                    ),
                    Course(
                        id="course-other",
                        user_id="u6",
                        name="自然语言处理",
                        location="会展-324",
                        weekday=4,
                        start_time="08:30",
                        end_time="10:05",
                    ),
                ]
            )
            await db.commit()

            first_round_events = []
            generator = run_agent_loop(
                "帮我删除自然语言处理里会展-305这门课",
                user,
                session_id,
                db,
                mock_client,
            )
            async for event in generator:
                first_round_events.append(event)

            second_round_events = []
            generator = run_agent_loop("你继续", user, session_id, db, mock_client)
            async for event in generator:
                second_round_events.append(event)

            first_types = [event["type"] for event in first_round_events]
            assert first_types == ["tool_call", "tool_result", "text", "done"]

            second_types = [event["type"] for event in second_round_events]
            assert "tool_call" in second_types
            delete_call = next(
                event
                for event in second_round_events
                if event["type"] == "tool_call" and event["name"] == "delete_course"
            )
            assert delete_call["args"] == {"course_id": target_course_id}

            message_result = await db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.session_id == session_id)
                .order_by(ConversationMessage.timestamp)
            )
            stored_messages = list(message_result.scalars().all())
            persisted_summaries = [
                message
                for message in stored_messages
                if message.role == "assistant"
                and message.is_compressed
                and message.content.startswith("[TOOL_SUMMARY:list_courses:v1] ")
            ]
            assert persisted_summaries
