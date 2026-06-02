from datetime import datetime
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.agent.tool_executor import execute_tool
from app.models.course import Course
from app.models.task import Task
from app.models.user import User


@pytest_asyncio.fixture
async def setup_course_and_task(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="user-sched-1",
            username="scheduser",
            hashed_password="x",
        )
        db.add(user)

        course = Course(
            id="course-sched-1",
            user_id="user-sched-1",
            name="线性代数",
            weekday=2,
            start_time="14:00",
            end_time="15:40",
            location="理学楼B201",
        )
        db.add(course)

        task = Task(
            id="task-sched-1",
            user_id="user-sched-1",
            title="复习概率论",
            scheduled_date="2026-04-02",
            start_time="10:00",
            end_time="12:00",
            status="pending",
        )
        db.add(task)
        await db.commit()

    yield


@pytest.mark.asyncio
@patch("app.agent.tool_executor.schedule_reminder_job")
async def test_set_reminder_task_schedules_job(mock_schedule, setup_course_and_task):
    from tests.conftest import TestSession

    async with TestSession() as db:
        result = await execute_tool(
            "set_reminder",
            {"target_type": "task", "target_id": "task-sched-1", "advance_minutes": 30},
            db,
            "user-sched-1",
        )

    assert result["status"] == "reminder_set"
    assert result["advance_minutes"] == 30
    assert result["remind_at"] == "2026-04-02T09:30:00"
    mock_schedule.assert_called_once()
    assert mock_schedule.call_args.kwargs["user_id"] == "user-sched-1"


@pytest.mark.asyncio
@patch("app.agent.tool_executor.next_course_occurrence")
@patch("app.agent.tool_executor.schedule_reminder_job")
async def test_set_reminder_course_uses_next_occurrence(mock_schedule, mock_occurrence, setup_course_and_task):
    from tests.conftest import TestSession

    mock_occurrence.return_value = datetime(2026, 4, 7, 14, 0)

    async with TestSession() as db:
        result = await execute_tool(
            "set_reminder",
            {"target_type": "course", "target_id": "course-sched-1", "advance_minutes": 15},
            db,
            "user-sched-1",
        )

    assert result["remind_at"] == "2026-04-07T13:45:00"
    assert result["advance_minutes"] == 15
    mock_occurrence.assert_called_once()
    mock_schedule.assert_called_once()
