from unittest.mock import AsyncMock, patch

import pytest

from app.agent.loop import run_agent_loop
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
