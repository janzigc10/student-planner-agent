from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.agent.tool_executor import execute_tool
from app.models.reminder import Reminder
from app.models.user import User
from tests.conftest import TestSession


@pytest.mark.asyncio
async def test_execute_unknown_tool(setup_db):
    """Unknown tool returns error."""
    async with TestSession() as db:
        result = await execute_tool("nonexistent_tool", {}, db, "user-1")
        assert "error" in result
        assert "Unknown tool" in result["error"]


@pytest.mark.asyncio
async def test_list_courses_empty(setup_db):
    async with TestSession() as db:
        result = await execute_tool("list_courses", {}, db, "user-1")
        assert result["count"] == 0
        assert result["courses"] == []


@pytest.mark.asyncio
async def test_add_and_list_course(setup_db):
    async with TestSession() as db:
        user = User(id="user-1", username="test", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "add_course",
            {
                "name": "高等数学",
                "weekday": 1,
                "start_time": "08:00",
                "end_time": "09:40",
            },
            db,
            "user-1",
        )
        assert result["status"] == "created"

        result = await execute_tool("list_courses", {}, db, "user-1")
        assert result["count"] == 1
        assert result["courses"][0]["name"] == "高等数学"


@pytest.mark.asyncio
async def test_create_task_creates_pending_task(setup_db):
    async with TestSession() as db:
        user = User(id="user-task-1", username="task-user", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "create_task",
            {
                "title": "做饭",
                "scheduled_date": "2026-05-02",
                "start_time": "17:00",
                "end_time": "17:30",
            },
            db,
            "user-task-1",
        )
        assert result["status"] == "created"
        assert result["title"] == "做饭"
        assert result["scheduled_date"] == "2026-05-02"
        assert result["start_time"] == "17:00"
        assert result["end_time"] == "17:30"

        listed = await execute_tool(
            "list_tasks",
            {"date_from": "2026-05-02", "date_to": "2026-05-02"},
            db,
            "user-task-1",
        )
        assert listed["count"] == 1
        assert listed["tasks"][0]["title"] == "做饭"
        assert listed["tasks"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_create_task_rejects_time_conflict(setup_db):
    async with TestSession() as db:
        user = User(id="user-task-2", username="task-user-2", hashed_password="x")
        db.add(user)
        await db.commit()

        created = await execute_tool(
            "create_task",
            {
                "title": "复习数据结构",
                "scheduled_date": "2026-05-02",
                "start_time": "13:00",
                "end_time": "15:00",
            },
            db,
            "user-task-2",
        )
        assert created["status"] == "created"

        conflict = await execute_tool(
            "create_task",
            {
                "title": "做饭",
                "scheduled_date": "2026-05-02",
                "start_time": "14:00",
                "end_time": "15:30",
            },
            db,
            "user-task-2",
        )
        assert "error" in conflict
        assert "conflict" in conflict["error"].lower()


@pytest.mark.asyncio
@patch("app.agent.tool_executor.schedule_reminder_job")
async def test_create_task_can_create_integrated_reminder(mock_schedule, setup_db):
    async with TestSession() as db:
        user = User(id="user-task-reminder-1", username="task-reminder-user", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "create_task",
            {
                "title": "review linear algebra",
                "scheduled_date": "2026-05-02",
                "start_time": "17:00",
                "end_time": "17:30",
                "reminder_advance_minutes": 30,
            },
            db,
            "user-task-reminder-1",
        )

        assert result["status"] == "created"
        assert result["task"]["title"] == "review linear algebra"
        assert result["reminders"][0]["advance_minutes"] == 30
        assert result["reminders"][0]["remind_at"] == "2026-05-02T16:30:00"
        mock_schedule.assert_called_once()

        reminder_result = await db.execute(
            select(Reminder).where(Reminder.user_id == "user-task-reminder-1")
        )
        reminder = reminder_result.scalar_one()
        assert reminder.target_type == "task"
        assert reminder.advance_minutes == 30
        assert reminder.remind_at == "2026-05-02T16:30:00"


@pytest.mark.asyncio
@patch("app.agent.tool_executor.schedule_reminder_job")
async def test_update_task_can_update_time_and_reminder_together(mock_schedule, setup_db):
    async with TestSession() as db:
        user = User(id="user-task-reminder-2", username="task-reminder-user-2", hashed_password="x")
        db.add(user)
        await db.commit()

        created = await execute_tool(
            "create_task",
            {
                "title": "review probability",
                "scheduled_date": "2026-05-02",
                "start_time": "10:00",
                "end_time": "11:00",
                "reminder_advance_minutes": 15,
            },
            db,
            "user-task-reminder-2",
        )
        mock_schedule.reset_mock()

        updated = await execute_tool(
            "update_task",
            {
                "task_id": created["id"],
                "scheduled_date": "2026-05-03",
                "start_time": "15:00",
                "end_time": "16:00",
                "reminder_advance_minutes": 30,
            },
            db,
            "user-task-reminder-2",
        )

        assert updated["status"] == "updated"
        assert updated["task"]["scheduled_date"] == "2026-05-03"
        assert updated["task"]["start_time"] == "15:00"
        assert updated["reminders"][0]["advance_minutes"] == 30
        assert updated["reminders"][0]["remind_at"] == "2026-05-03T14:30:00"
        mock_schedule.assert_called_once()

        reminder_result = await db.execute(
            select(Reminder).where(Reminder.user_id == "user-task-reminder-2")
        )
        reminder = reminder_result.scalar_one()
        assert reminder.target_id == created["id"]
        assert reminder.advance_minutes == 30
        assert reminder.remind_at == "2026-05-03T14:30:00"


@pytest.mark.asyncio
async def test_update_course_changes_name(setup_db):
    async with TestSession() as db:
        user = User(id="user-update-1", username="test-update", hashed_password="x")
        db.add(user)
        await db.commit()

        created = await execute_tool(
            "add_course",
            {
                "name": "机器人程序动化",
                "weekday": 3,
                "start_time": "10:20",
                "end_time": "11:55",
                "week_pattern": "even",
            },
            db,
            "user-update-1",
        )
        assert created["status"] == "created"

        updated = await execute_tool(
            "update_course",
            {
                "course_id": created["id"],
                "name": "机器人流程自动化",
            },
            db,
            "user-update-1",
        )
        assert updated["status"] == "updated"
        assert updated["name"] == "机器人流程自动化"

        result = await execute_tool("list_courses", {}, db, "user-update-1")
        assert result["count"] == 1
        assert result["courses"][0]["name"] == "机器人流程自动化"
        assert result["courses"][0]["week_pattern"] == "even"


@pytest.mark.asyncio
async def test_ask_user_returns_action(setup_db):
    async with TestSession() as db:
        result = await execute_tool(
            "ask_user",
            {
                "question": "确认吗？",
                "type": "confirm",
            },
            db,
            "user-1",
        )
        assert result["action"] == "ask_user"
        assert result["question"] == "确认吗？"
