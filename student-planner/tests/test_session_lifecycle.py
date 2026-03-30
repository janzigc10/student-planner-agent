import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.session_lifecycle import end_session
from app.models.conversation_message import ConversationMessage
from app.models.memory import Memory
from app.models.session_summary import SessionSummary
from app.models.user import User


@pytest.mark.asyncio
async def test_end_session_creates_summary(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-1", username="sesstest1", hashed_password="x")
        db.add(user)
        db.add_all(
            [
                ConversationMessage(session_id="sess-1", role="user", content="我想安排这周的复习计划"),
                ConversationMessage(session_id="sess-1", role="assistant", content="好，我先看看你的空闲时间。"),
                ConversationMessage(session_id="sess-1", role="user", content="周三晚上我也有空"),
                ConversationMessage(session_id="sess-1", role="assistant", content="好的，我把周三晚上的时间也考虑进去。"),
            ]
        )
        await db.commit()

        mock_summary_response = {
            "role": "assistant",
            "content": json.dumps(
                {
                    "summary": "我们确认了本周复习计划，并把周三晚上的空闲时间也纳入安排。",
                    "actions": ["查看空闲时间", "更新复习安排"],
                    "memories": [],
                },
                ensure_ascii=False,
            ),
        }

        with patch(
            "app.agent.session_lifecycle.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_summary_response,
        ):
            await end_session(db, "sess-user-1", "sess-1", AsyncMock())

        result = await db.execute(select(SessionSummary).where(SessionSummary.session_id == "sess-1"))
        summary = result.scalar_one_or_none()
        assert summary is not None
        assert "周三晚上" in summary.summary


@pytest.mark.asyncio
async def test_end_session_extracts_memories(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-2", username="sesstest2", hashed_password="x")
        db.add(user)
        db.add_all(
            [
                ConversationMessage(session_id="sess-2", role="user", content="我更喜欢晚上安排复习"),
                ConversationMessage(session_id="sess-2", role="assistant", content="好，我记下来了。"),
            ]
        )
        await db.commit()

        mock_response = {
            "role": "assistant",
            "content": json.dumps(
                {
                    "summary": "用户说明自己更喜欢晚上安排复习。",
                    "actions": [],
                    "memories": [
                        {"category": "preference", "content": "更喜欢晚上安排复习"}
                    ],
                },
                ensure_ascii=False,
            ),
        }

        with patch(
            "app.agent.session_lifecycle.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            await end_session(db, "sess-user-2", "sess-2", AsyncMock())

        result = await db.execute(select(Memory).where(Memory.user_id == "sess-user-2"))
        memories = result.scalars().all()
        assert len(memories) == 1
        assert memories[0].category == "preference"
        assert "晚上安排复习" in memories[0].content
        assert memories[0].source_session_id == "sess-2"


@pytest.mark.asyncio
async def test_end_session_empty_conversation(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-3", username="sesstest3", hashed_password="x")
        db.add(user)
        await db.commit()

        await end_session(db, "sess-user-3", "sess-3", AsyncMock())

        result = await db.execute(select(SessionSummary).where(SessionSummary.session_id == "sess-3"))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_end_session_handles_llm_error(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-4", username="sesstest4", hashed_password="x")
        db.add(user)
        db.add(ConversationMessage(session_id="sess-4", role="user", content="hello"))
        await db.commit()

        with patch(
            "app.agent.session_lifecycle.chat_completion",
            new_callable=AsyncMock,
            side_effect=Exception("LLM down"),
        ):
            await end_session(db, "sess-user-4", "sess-4", AsyncMock())

        result = await db.execute(select(SessionSummary).where(SessionSummary.session_id == "sess-4"))
        assert result.scalar_one_or_none() is None