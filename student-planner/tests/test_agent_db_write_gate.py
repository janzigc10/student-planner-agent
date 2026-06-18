from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.agent.contracts import AgentRoute, DBWritePlan, PendingConfirmation
from app.agent.loop import _execute_confirmed_db_write_plan
from app.models.course import Course
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from tests.conftest import TestSession


def _pending(
    *,
    confirmation_id: str = "confirm-1",
    route: str = AgentRoute.TOOL_WORKFLOW.value,
    tool_name: str = "create_task",
    allowed_tool_names: list[str] | None = None,
) -> PendingConfirmation:
    return PendingConfirmation(
        confirmation_id=confirmation_id,
        route=route,
        tool_name=tool_name,
        ask_type="confirm",
        question="确认写入吗？",
        options=("确认", "取消"),
        allowed_tool_names=tuple(allowed_tool_names or ()),
    )


def _plan(
    *,
    confirmation_id: str = "confirm-1",
    route: str = AgentRoute.TOOL_WORKFLOW.value,
    tool_name: str = "create_task",
    args: dict | None = None,
) -> DBWritePlan:
    return DBWritePlan(
        confirmation_id=confirmation_id,
        route=route,
        tool_name=tool_name,
        args=args
        or {
            "title": "受保护任务",
            "scheduled_date": "2099-06-01",
            "start_time": "09:00",
            "end_time": "10:00",
        },
        description="protected write",
    )


@pytest.mark.asyncio
async def test_db_write_gate_blocks_missing_state_for_core_write_tools(setup_db):
    async with TestSession() as db:
        user = User(id="gate-missing-user", username="gate-missing-user", hashed_password="x")
        task = Task(
            id="gate-missing-task",
            user_id=user.id,
            title="existing task",
            scheduled_date="2099-06-01",
            start_time="10:00",
            end_time="11:00",
        )
        course = Course(
            id="gate-missing-course",
            user_id=user.id,
            name="旧课程",
            weekday=1,
            start_time="08:00",
            end_time="09:00",
        )
        db.add_all([user, task, course])
        await db.commit()

        cases = [
            ("create_task", {"title": "blocked", "scheduled_date": "2099-06-01"}),
            ("update_task", {"task_id": task.id, "title": "blocked update"}),
            ("set_reminder", {"target_type": "task", "target_id": task.id, "advance_minutes": 0}),
            ("bulk_import_courses", {"courses": [{"name": "blocked course", "weekday": 2}]}),
            ("update_course", {"course_id": course.id, "name": "blocked course update"}),
            ("delete_course", {"course_id": course.id}),
        ]

        for tool_name, args in cases:
            result = await _execute_confirmed_db_write_plan(
                pending_confirmation=None,
                db_write_plan=_plan(tool_name=tool_name, args=args),
                confirmation_answer="确认",
                db=db,
                user_id=user.id,
            )
            assert "error" in result

        tasks = list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all())
        courses = list((await db.execute(select(Course).where(Course.user_id == user.id))).scalars().all())
        reminders = list((await db.execute(select(Reminder).where(Reminder.user_id == user.id))).scalars().all())
        assert [(task.title, task.start_time) for task in tasks] == [("existing task", "10:00")]
        assert [(course.id, course.name) for course in courses] == [(course.id, "旧课程")]
        assert reminders == []


@pytest.mark.asyncio
async def test_db_write_gate_rejects_route_mismatch_before_create_task(setup_db):
    async with TestSession() as db:
        user = User(id="gate-route-user", username="gate-route-user", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await _execute_confirmed_db_write_plan(
            pending_confirmation=_pending(route=AgentRoute.STUDY_PLAN.value),
            db_write_plan=_plan(route=AgentRoute.TOOL_WORKFLOW.value),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )

        assert result["error"] == "Confirmation state does not match database write plan."
        tasks = list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all())
        assert tasks == []


@pytest.mark.asyncio
@patch("app.agent.tool_executor.schedule_reminder_job")
async def test_db_write_gate_allows_confirmed_task_plus_reminder_chain(mock_schedule, setup_db):
    async with TestSession() as db:
        user = User(id="gate-chain-user", username="gate-chain-user", hashed_password="x")
        db.add(user)
        await db.commit()

        pending = _pending(
            tool_name="create_task",
            allowed_tool_names=["create_task", "set_reminder"],
        )
        created = await _execute_confirmed_db_write_plan(
            pending_confirmation=pending,
            db_write_plan=_plan(tool_name="create_task"),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )
        assert created["status"] == "created"

        reminder = await _execute_confirmed_db_write_plan(
            pending_confirmation=pending,
            db_write_plan=_plan(
                tool_name="set_reminder",
                args={"target_type": "task", "target_id": created["id"], "advance_minutes": 0},
            ),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )
        assert reminder["status"] == "reminder_set"
        mock_schedule.assert_called_once()

        reminders = list((await db.execute(select(Reminder).where(Reminder.user_id == user.id))).scalars().all())
        assert len(reminders) == 1
        assert reminders[0].target_id == created["id"]


@pytest.mark.asyncio
async def test_db_write_gate_blocks_tool_mismatch_not_in_confirmation_scope(setup_db):
    async with TestSession() as db:
        user = User(id="gate-tool-user", username="gate-tool-user", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await _execute_confirmed_db_write_plan(
            pending_confirmation=_pending(tool_name="create_task", allowed_tool_names=["create_task"]),
            db_write_plan=_plan(tool_name="set_reminder", args={"target_type": "task", "target_id": "missing"}),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )

        assert result["error"] == "Confirmation state does not match database write plan."
        reminders = list((await db.execute(select(Reminder).where(Reminder.user_id == user.id))).scalars().all())
        assert reminders == []
