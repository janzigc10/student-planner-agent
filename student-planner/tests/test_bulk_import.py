from unittest.mock import patch

from sqlalchemy import select

import pytest

from app.agent.tool_executor import execute_tool
from app.agent.tools import TOOL_DEFINITIONS
from app.models.course import Course
from app.models.reminder import Reminder
from app.models.user import User


def test_bulk_import_tool_defined() -> None:
    names = [tool["function"]["name"] for tool in TOOL_DEFINITIONS]
    assert "bulk_import_courses" in names


@pytest.mark.asyncio
async def test_bulk_import_creates_courses(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="test-user-1", username="bulktest", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "bulk_import_courses",
            {
                "courses": [
                    {
                        "name": "高等数学",
                        "teacher": "张老师",
                        "location": "教学楼A301",
                        "weekday": 1,
                        "start_time": "08:00",
                        "end_time": "09:40",
                        "week_start": 1,
                        "week_end": 16,
                    },
                    {
                        "name": "线性代数",
                        "weekday": 3,
                        "start_time": "10:00",
                        "end_time": "11:40",
                    },
                ]
            },
            db=db,
            user_id="test-user-1",
        )

        assert result["status"] == "imported"
        assert result["count"] == 2

        courses_result = await db.execute(select(Course).where(Course.user_id == "test-user-1"))
        courses = courses_result.scalars().all()
        assert len(courses) == 2
        names = {course.name for course in courses}
        assert "高等数学" in names
        assert "线性代数" in names


@pytest.mark.asyncio
async def test_bulk_import_empty_list(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="test-user-2", username="bulktest2", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "bulk_import_courses",
            {"courses": []},
            db=db,
            user_id="test-user-2",
        )
        assert result["status"] == "imported"
        assert result["count"] == 0


@pytest.mark.asyncio
async def test_bulk_import_uses_default_reminder_minutes_preference(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="test-user-3",
            username="bulktest3",
            hashed_password="x",
            preferences={"default_reminder_minutes": 30},
        )
        db.add(user)
        await db.commit()

        await execute_tool(
            "bulk_import_courses",
            {
                "courses": [
                    {
                        "name": "概率论",
                        "weekday": 4,
                        "start_time": "14:00",
                        "end_time": "15:40",
                    }
                ]
            },
            db=db,
            user_id="test-user-3",
        )

        reminders_result = await db.execute(select(Reminder).where(Reminder.user_id == "test-user-3"))
        reminder = reminders_result.scalar_one()
        assert reminder.advance_minutes == 30


@pytest.mark.asyncio
async def test_bulk_import_preserves_week_pattern_and_text(setup_db) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="test-user-4", username="bulktest4", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "bulk_import_courses",
            {
                "courses": [
                    {
                        "name": "practice-course",
                        "weekday": 1,
                        "start_time": "08:00",
                        "end_time": "09:40",
                        "week_start": 1,
                        "week_end": 18,
                        "week_pattern": "odd",
                        "week_text": "Week 1-18 (odd)",
                    }
                ]
            },
            db=db,
            user_id="test-user-4",
        )

        assert result["status"] == "imported"

        courses_result = await db.execute(select(Course).where(Course.user_id == "test-user-4"))
        course = courses_result.scalar_one()
        assert course.week_pattern == "odd"
        assert course.week_text == "Week 1-18 (odd)"


@pytest.mark.asyncio
@patch("app.agent.tool_executor.next_course_occurrence", return_value=None)
async def test_bulk_import_skips_reminder_when_course_has_no_active_occurrence(
    mock_occurrence,
    setup_db,
) -> None:
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="test-user-5", username="bulktest5", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "bulk_import_courses",
            {
                "courses": [
                    {
                        "name": "ended-course",
                        "weekday": 1,
                        "start_time": "08:00",
                        "end_time": "09:40",
                        "week_start": 1,
                        "week_end": 1,
                    }
                ]
            },
            db=db,
            user_id="test-user-5",
        )

        assert result["status"] == "imported"
        assert result["reminders_created"] == 0
        mock_occurrence.assert_called_once()

        reminders_result = await db.execute(select(Reminder).where(Reminder.user_id == "test-user-5"))
        assert list(reminders_result.scalars().all()) == []
