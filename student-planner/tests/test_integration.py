from unittest.mock import AsyncMock, patch

import pytest

from app.agent.loop import run_agent_loop
from app.models.course import Course
from app.models.user import User
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_full_flow_list_courses(setup_db):
    """User asks what courses they have, agent calls list_courses, then responds."""
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
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "list_courses", "arguments": "{}"},
                    }
                ],
            }
        return {"role": "assistant", "content": "你有1门课：高等数学，周一 08:00-09:40。"}

    with patch("app.agent.loop.chat_completion", side_effect=mock_chat_completion):
        async with TestSession() as db:
            user = User(id="u-int", username="inttest", hashed_password="x")
            db.add(user)
            course = Course(
                user_id="u-int",
                name="高等数学",
                weekday=1,
                start_time="08:00",
                end_time="09:40",
            )
            db.add(course)
            await db.commit()

            events = []
            generator = run_agent_loop("我有什么课", user, "s-int", db, AsyncMock())
            async for event in generator:
                events.append(event)

            types = [event["type"] for event in events]
            assert "tool_call" in types
            assert "tool_result" in types
            assert "text" in types
            assert "done" in types

            tool_result_event = next(event for event in events if event["type"] == "tool_result")
            assert tool_result_event["result"]["count"] == 1