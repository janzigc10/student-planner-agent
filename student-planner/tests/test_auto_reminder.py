from datetime import datetime
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agent.tool_executor import execute_tool
from app.models.reminder import Reminder
from app.models.user import User


@pytest_asyncio.fixture
async def setup_import_user(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="user-import-1",
            username="importuser",
            hashed_password="x",
        )
        db.add(user)
        await db.commit()

    yield


@pytest.mark.asyncio
@patch("app.agent.tool_executor.next_course_occurrence")
@patch("app.agent.tool_executor.schedule_reminder_job")
async def test_bulk_import_creates_reminders(mock_schedule, mock_occurrence, setup_import_user):
    from tests.conftest import TestSession

    mock_occurrence.side_effect = [
        datetime(2026, 4, 7, 8, 0),
        datetime(2026, 4, 9, 10, 0),
    ]
    courses_data = [
        {
            "name": "高等数学",
            "weekday": 1,
            "start_time": "08:00",
            "end_time": "09:40",
            "location": "教学楼A301",
        },
        {
            "name": "线性代数",
            "weekday": 3,
            "start_time": "10:00",
            "end_time": "11:40",
            "location": "理学楼B201",
        },
    ]

    async with TestSession() as db:
        result = await execute_tool(
            "bulk_import_courses",
            {"courses": courses_data},
            db,
            "user-import-1",
        )

    assert result["status"] == "imported"
    assert result["count"] == 2
    assert result["reminders_created"] == 2

    async with TestSession() as db:
        rem_result = await db.execute(
            select(Reminder).where(Reminder.user_id == "user-import-1")
        )
        reminders = list(rem_result.scalars().all())
        assert len(reminders) == 2
        assert all(r.target_type == "course" for r in reminders)
        assert all(r.advance_minutes == 15 for r in reminders)


@pytest.mark.asyncio
@patch("app.agent.tool_executor.next_course_occurrence")
@patch("app.agent.tool_executor.schedule_reminder_job")
async def test_bulk_import_reminder_stores_trigger_time(mock_schedule, mock_occurrence, setup_import_user):
    from tests.conftest import TestSession

    mock_occurrence.return_value = datetime(2026, 4, 11, 14, 0)
    courses_data = [
        {
            "name": "概率论",
            "weekday": 5,
            "start_time": "14:00",
            "end_time": "15:40",
        },
    ]

    async with TestSession() as db:
        await execute_tool(
            "bulk_import_courses",
            {"courses": courses_data},
            db,
            "user-import-1",
        )

    async with TestSession() as db:
        rem_result = await db.execute(
            select(Reminder).where(Reminder.user_id == "user-import-1")
        )
        reminder = rem_result.scalar_one()
        assert reminder.remind_at == "2026-04-11T13:45:00"
        assert reminder.advance_minutes == 15
