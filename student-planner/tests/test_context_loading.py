import pytest

from app.agent.context import build_dynamic_context
from app.models.memory import Memory
from app.models.session_summary import SessionSummary
from app.models.user import User


@pytest.mark.asyncio
async def test_hot_memories_in_context(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-1", username="ctxtest1", hashed_password="x")
        db.add(user)
        db.add_all(
            [
                Memory(user_id="ctx-user-1", category="preference", content="喜欢早上复习数学"),
                Memory(user_id="ctx-user-1", category="habit", content="一次最多专注 1 小时"),
            ]
        )
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "喜欢早上复习数学" in context
        assert "一次最多专注 1 小时" in context


@pytest.mark.asyncio
async def test_warm_memories_in_context(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-2", username="ctxtest2", hashed_password="x")
        db.add(user)
        db.add(Memory(user_id="ctx-user-2", category="decision", content="高数复习采用分章节策略"))
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "高数复习采用分章节策略" in context


@pytest.mark.asyncio
async def test_no_memories_still_works(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-3", username="ctxtest3", hashed_password="x")
        db.add(user)
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "当前时间" in context
        assert "褰撳墠鏃堕棿" not in context
        assert "浠婂ぉ鐨勬棩绋嬶細" not in context


@pytest.mark.asyncio
async def test_last_session_summary_in_context(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-4", username="ctxtest4", hashed_password="x")
        db.add(user)
        db.add(
            SessionSummary(
                user_id="ctx-user-4",
                session_id="prev-session",
                summary="上次我们已经确认了高数复习计划。",
            )
        )
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "上次我们已经确认了高数复习计划。" in context
