from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.agent.contracts import AgentRoute, DBWritePlan, PendingConfirmation, stable_args_digest
from app.agent.loop import (
    _build_confirmed_write_state_from_ask,
    _execute_confirmed_db_write_plan,
    _is_confirmed_answer,
    _restore_confirmed_task_reminder_arg,
)
from app.agent.tool_executor import execute_tool, execute_tool_batch
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
    data: dict | None = None,
    planned_args: list[dict] | None = None,
    ask_type: str = "confirm",
) -> PendingConfirmation:
    return PendingConfirmation(
        confirmation_id=confirmation_id,
        route=route,
        tool_name=tool_name,
        ask_type=ask_type,
        question="确认写入吗？",
        options=("确认", "取消"),
        data=data,
        allowed_tool_names=tuple(allowed_tool_names or ()),
        planned_args=tuple(planned_args or ()),
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


def test_confirmed_task_write_restores_reminder_from_pending_confirmation():
    pending = _pending(data={"reminder_advance_minutes": 30})

    restored = _restore_confirmed_task_reminder_arg(
        tool_name="create_task",
        args={
            "title": "review",
            "scheduled_date": "2099-06-01",
            "start_time": "09:00",
            "end_time": "10:00",
            "reminder_advance_minutes": None,
        },
        pending_confirmation=pending,
        confirmation_answer="ok",
    )

    assert restored["reminder_advance_minutes"] == 30


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

        create_args = _plan().args
        pending = _pending(
            tool_name="create_task",
            allowed_tool_names=["create_task"],
            planned_args=[dict(create_args)],
        )
        created = await _execute_confirmed_db_write_plan(
            pending_confirmation=pending,
            db_write_plan=_plan(tool_name="create_task"),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )
        assert created["status"] == "created"

        reminder_args = {"target_type": "task", "target_id": created["id"], "advance_minutes": 0}
        reminder = await _execute_confirmed_db_write_plan(
            pending_confirmation=_pending(
                confirmation_id="confirm-reminder",
                tool_name="set_reminder",
                allowed_tool_names=["set_reminder"],
                planned_args=[reminder_args],
            ),
            db_write_plan=_plan(
                confirmation_id="confirm-reminder",
                tool_name="set_reminder",
                args=reminder_args,
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


@pytest.mark.asyncio
async def test_db_write_gate_rejects_confirmation_a_with_plan_b_args(setup_db):
    async with TestSession() as db:
        user = User(id="gate-args-user", username="gate-args-user", hashed_password="x")
        db.add(user)
        await db.commit()

        confirmed_args = {
            "title": "confirmed task",
            "scheduled_date": "2099-06-01",
            "start_time": "09:00",
            "end_time": "10:00",
        }
        result = await _execute_confirmed_db_write_plan(
            pending_confirmation=_pending(planned_args=[confirmed_args]),
            db_write_plan=_plan(
                args={**confirmed_args, "title": "tampered task"},
            ),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )

        assert result["error"] == "Confirmation state does not match database write plan."
        tasks = list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all())
        assert tasks == []


@pytest.mark.asyncio
async def test_db_write_gate_consumes_same_ticket_once(setup_db):
    async with TestSession() as db:
        user = User(id="gate-replay-user", username="gate-replay-user", hashed_password="x")
        db.add(user)
        await db.commit()

        args = {
            "title": "only once",
            "scheduled_date": "2099-06-01",
            "start_time": "09:00",
            "end_time": "10:00",
        }
        pending = _pending(planned_args=[args])
        plan = _plan(args=args)
        first = await _execute_confirmed_db_write_plan(
            pending_confirmation=pending,
            db_write_plan=plan,
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )
        second = await _execute_confirmed_db_write_plan(
            pending_confirmation=pending,
            db_write_plan=plan,
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )

        assert first["status"] == "created"
        assert second["error"] == "Confirmation ticket has already been consumed."
        tasks = list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all())
        assert len(tasks) == 1


@pytest.mark.asyncio
async def test_db_write_gate_rejects_confirmation_without_planned_args(setup_db):
    async with TestSession() as db:
        user = User(id="gate-empty-plan-user", username="gate-empty-plan-user", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await _execute_confirmed_db_write_plan(
            pending_confirmation=_pending(),
            db_write_plan=_plan(),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )

        assert result["error"] == "Confirmation state does not match database write plan."
        assert list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all()) == []


@pytest.mark.asyncio
async def test_review_text_is_not_write_authorization(setup_db):
    async with TestSession() as db:
        user = User(id="gate-review-question-user", username="gate-review-question-user", hashed_password="x")
        db.add(user)
        await db.commit()

        args = {
            "title": "review question task",
            "scheduled_date": "2099-06-01",
            "start_time": "09:00",
            "end_time": "10:00",
        }
        result = await _execute_confirmed_db_write_plan(
            pending_confirmation=_pending(planned_args=[args], ask_type="review"),
            db_write_plan=_plan(args=args),
            confirmation_answer="为什么这样安排？",
            db=db,
            user_id=user.id,
        )

        assert result["status"] == "cancelled"
        assert list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all()) == []


def test_db_write_plan_freezes_nested_args_and_detects_digest_mismatch():
    plan = _plan(args={"title": "nested", "meta": {"labels": ["confirmed"]}})

    with pytest.raises((TypeError, AttributeError)):
        plan.args["meta"]["labels"].append("tampered")

    object.__setattr__(plan, "args", {"title": "nested", "meta": {"labels": ["tampered"]}})
    assert plan.args_digest != stable_args_digest(plan.args)


def test_generic_ask_without_structured_plan_cannot_create_confirmation_ticket():
    pending = _build_confirmed_write_state_from_ask(
        tool_args={"question": "确认创建任务？", "type": "confirm"},
        ask_result={"question": "确认创建任务？", "type": "confirm", "data": None},
        confirmation_answer="确认",
    )

    assert pending is None


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("确认", True),
        ("可以", True),
        ('确认 review_override={"tasks": []}', True),
        ("好像不对，先别创建", False),
        ("行程不对，取消", False),
        ("是这样，但我想取消", False),
        ("取消", False),
    ],
)
def test_write_confirmation_requires_an_explicit_choice(answer, expected):
    assert _is_confirmed_answer(answer) is expected


@pytest.mark.asyncio
async def test_derived_reschedule_cannot_bypass_confirmation_digest(setup_db):
    async with TestSession() as db:
        user = User(id="gate-derived-reschedule-user", username="gate-derived-reschedule-user", hashed_password="x")
        db.add(user)
        await db.commit()

        original = dict(_plan().args)
        derived = {**original, "start_time": "11:00", "end_time": "12:00"}
        result = await _execute_confirmed_db_write_plan(
            pending_confirmation=_pending(planned_args=[original]),
            db_write_plan=_plan(args=derived),
            confirmation_answer="确认",
            db=db,
            user_id=user.id,
        )

        assert result["error"] == "Confirmation state does not match database write plan."
        assert list((await db.execute(select(Task).where(Task.user_id == user.id))).scalars().all()) == []


@pytest.mark.asyncio
async def test_bulk_import_rolls_back_all_rows_when_later_course_is_invalid(setup_db):
    async with TestSession() as db:
        user = User(id="bulk-rollback-user", username="bulk-rollback-user", hashed_password="x")
        user_id = user.id
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "bulk_import_courses",
            {
                "courses": [
                    {
                        "name": "first course",
                        "weekday": 1,
                        "start_time": "09:00",
                        "end_time": "10:00",
                    },
                    {
                        "name": "invalid second course",
                        "weekday": 2,
                    },
                ]
            },
            db,
            user_id,
        )

        assert "error" in result
        courses = list((await db.execute(select(Course).where(Course.user_id == user_id))).scalars().all())
        assert courses == []


@pytest.mark.asyncio
async def test_mixed_course_update_delete_batch_rolls_back_first_update_on_second_failure(setup_db):
    async with TestSession() as db:
        user = User(id="mixed-course-batch-user", username="mixed-course-batch-user", hashed_password="x")
        course = Course(
            id="mixed-course-batch-course",
            user_id=user.id,
            name="original course",
            weekday=1,
            start_time="08:00",
            end_time="09:00",
        )
        db.add_all([user, course])
        await db.commit()

        result = await execute_tool_batch(
            [
                ("update_course", {"course_id": course.id, "name": "updated course"}),
                ("delete_course", {"course_id": "missing-course"}),
            ],
            db,
            user.id,
        )

        assert result["status"] == "rolled_back"
        await db.refresh(course)
        assert course.name == "original course"


@pytest.mark.asyncio
async def test_batch_rollback_does_not_schedule_or_persist_task_reminder(setup_db):
    async with TestSession() as db:
        user = User(id="batch-effect-user", username="batch-effect-user", hashed_password="x")
        task = Task(
            id="batch-effect-task",
            user_id=user.id,
            title="existing task",
            scheduled_date="2099-06-01",
            start_time="09:00",
            end_time="10:00",
        )
        db.add_all([user, task])
        await db.commit()
        user_id = user.id
        task_id = task.id

        with patch("app.agent.tool_executor.schedule_reminder_job") as schedule_job:
            result = await execute_tool_batch(
                [
                    (
                        "set_reminder",
                        {
                            "target_type": "task",
                            "target_id": task_id,
                            "advance_minutes": 15,
                        },
                    ),
                    ("delete_course", {"course_id": "missing-course"}),
                ],
                db,
                user_id,
            )

        reminders = list(
            (await db.execute(select(Reminder).where(Reminder.user_id == user_id))).scalars().all()
        )
        assert result["status"] == "rolled_back"
        assert reminders == []
        schedule_job.assert_not_called()


@pytest.mark.asyncio
async def test_post_commit_scheduler_failure_keeps_db_fact_and_reports_partial_effect(setup_db):
    async with TestSession() as db:
        user = User(id="effect-failure-user", username="effect-failure-user", hashed_password="x")
        db.add(user)
        await db.commit()
        user_id = user.id

        with patch(
            "app.agent.tool_executor.schedule_reminder_job",
            side_effect=RuntimeError("scheduler unavailable"),
        ):
            result = await execute_tool(
                "create_task",
                {
                    "title": "committed task",
                    "scheduled_date": "2099-06-02",
                    "start_time": "09:00",
                    "end_time": "10:00",
                    "reminder_advance_minutes": 15,
                },
                db,
                user_id,
            )

        tasks = list((await db.execute(select(Task).where(Task.user_id == user_id))).scalars().all())
        reminders = list(
            (await db.execute(select(Reminder).where(Reminder.user_id == user_id))).scalars().all()
        )
        assert len(tasks) == 1
        assert len(reminders) == 1
        assert result["effect_status"] == "failed"
        assert "数据已保存" in result["effect_message"]
