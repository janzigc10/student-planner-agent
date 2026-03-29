from unittest.mock import MagicMock

import pytest

from app.agent.context import build_dynamic_context
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_context_includes_current_time(setup_db):
    user = MagicMock()
    user.id = "user-1"
    user.current_semester_start = None
    user.preferences = {}

    async with TestSession() as db:
        context = await build_dynamic_context(user, db)
        assert "当前时间" in context
        assert "今天的日程" in context


@pytest.mark.asyncio
async def test_context_includes_preferences(setup_db):
    user = MagicMock()
    user.id = "user-1"
    user.current_semester_start = None
    user.preferences = {"earliest_study": "08:00", "latest_study": "22:00"}

    async with TestSession() as db:
        context = await build_dynamic_context(user, db)
        assert "08:00" in context
        assert "22:00" in context