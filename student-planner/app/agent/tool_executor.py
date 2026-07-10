from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.study_planner import generate_study_plan
from app.agent.work_planner import generate_work_plan
from app.models.course import Course
from app.models.memory import Memory
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services.calendar import TimeSlot, compute_free_slots
from app.services.memory_service import (
    create_memory,
    delete_memory as delete_memory_record,
    recall_memories,
)
from app.services.reminder_scheduler import (
    cancel_reminder_job,
    resolve_fire_time,
    schedule_reminder_job,
)
from app.services.course_occurrence import course_occurs_on_date, next_course_occurrence
from app.services.period_converter import convert_periods, normalize_period, parse_time_range
from app.services.schedule_upload_cache import get_schedule_upload, update_schedule_upload_state


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    user_id: str,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    """Dispatch a tool call to the appropriate handler."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await handler(db=db, user_id=user_id, _commit=commit, **arguments)
    except Exception as exc:
        await db.rollback()
        return {"error": str(exc)}


async def execute_tool_batch(
    calls: list[tuple[str, dict[str, Any]]],
    db: AsyncSession,
    user_id: str,
) -> dict[str, Any]:
    """Run a preflighted write batch and commit it once, or rollback all rows."""

    results: list[dict[str, Any]] = []
    try:
        for tool_name, arguments in calls:
            result = await execute_tool(tool_name, arguments, db, user_id, commit=False)
            results.append(result)
            if "error" in result:
                await db.rollback()
                return {"status": "rolled_back", "results": results}
        await db.commit()
        return {"status": "committed", "results": results}
    except Exception as exc:
        await db.rollback()
        return {"status": "rolled_back", "results": results, "error": str(exc)}


async def _list_courses(db: AsyncSession, user_id: str, **kwargs) -> dict[str, Any]:
    result = await db.execute(select(Course).where(Course.user_id == user_id))
    courses = list(result.scalars().all())
    return {
        "courses": [
            {
                "id": course.id,
                "name": course.name,
                "teacher": course.teacher,
                "location": course.location,
                "weekday": course.weekday,
                "start_time": course.start_time,
                "end_time": course.end_time,
                "week_start": course.week_start,
                "week_end": course.week_end,
                "week_pattern": course.week_pattern,
                "week_text": course.week_text,
            }
            for course in courses
        ],
        "count": len(courses),
    }


def _build_course_week_text(week_start: int, week_end: int, week_pattern: str) -> str:
    if week_pattern == "odd":
        return f"Week {week_start}-{week_end} (odd)"
    if week_pattern == "even":
        return f"Week {week_start}-{week_end} (even)"
    return f"Week {week_start}-{week_end}"


def _normalize_course_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    week_start = int(normalized.get("week_start", 1))
    week_end = int(normalized.get("week_end", 16))
    if week_end < week_start:
        week_end = week_start
    week_pattern = str(normalized.get("week_pattern") or "all").lower()
    if week_pattern not in {"all", "odd", "even"}:
        week_pattern = "all"
    normalized["week_start"] = week_start
    normalized["week_end"] = week_end
    normalized["week_pattern"] = week_pattern
    normalized["week_text"] = normalized.get("week_text") or _build_course_week_text(
        week_start, week_end, week_pattern
    )
    return normalized


async def _add_course(db: AsyncSession, user_id: str, _commit: bool = True, **kwargs) -> dict[str, Any]:
    course = Course(user_id=user_id, **_normalize_course_payload(kwargs))
    db.add(course)
    if _commit:
        await db.commit()
        await db.refresh(course)
    else:
        await db.flush()
    return {"id": course.id, "name": course.name, "status": "created"}


async def _update_course(db: AsyncSession, user_id: str, course_id: str, _commit: bool = True, **kwargs) -> dict[str, Any]:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    course = result.scalar_one_or_none()
    if course is None:
        return {"error": "Course not found"}

    payload = {
        "name": course.name,
        "teacher": course.teacher,
        "location": course.location,
        "weekday": course.weekday,
        "start_time": course.start_time,
        "end_time": course.end_time,
        "week_start": course.week_start,
        "week_end": course.week_end,
        "week_pattern": course.week_pattern,
        "week_text": course.week_text,
    }
    payload.update(kwargs)
    normalized = _normalize_course_payload(payload)

    course.name = normalized["name"]
    course.teacher = normalized.get("teacher")
    course.location = normalized.get("location")
    course.weekday = normalized["weekday"]
    course.start_time = normalized["start_time"]
    course.end_time = normalized["end_time"]
    course.week_start = normalized["week_start"]
    course.week_end = normalized["week_end"]
    course.week_pattern = normalized["week_pattern"]
    course.week_text = normalized["week_text"]

    if _commit:
        await db.commit()
        await db.refresh(course)
    else:
        await db.flush()
    return {"id": course.id, "name": course.name, "status": "updated"}


async def _delete_course(db: AsyncSession, user_id: str, course_id: str, _commit: bool = True, **kwargs) -> dict[str, Any]:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    course = result.scalar_one_or_none()
    if course is None:
        return {"error": "Course not found"}

    await db.delete(course)
    if _commit:
        await db.commit()
    return {"status": "deleted", "name": course.name}


async def _get_free_slots(
    db: AsyncSession,
    user_id: str,
    start_date: str,
    end_date: str,
    min_duration_minutes: int = 30,
    **kwargs,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    semester_start = user.current_semester_start if user else None
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    days: list[dict[str, Any]] = []

    current = start
    while current <= end:
        weekday = current.isoweekday()
        date_str = current.isoformat()

        course_result = await db.execute(
            select(Course).where(Course.user_id == user_id, Course.weekday == weekday)
        )
        courses = [
            course
            for course in course_result.scalars().all()
            if course_occurs_on_date(course, current, semester_start)
        ]

        task_result = await db.execute(
            select(Task).where(
                Task.user_id == user_id,
                Task.scheduled_date == date_str,
                Task.status != "skipped",
            )
        )
        tasks = list(task_result.scalars().all())

        occupied: list[TimeSlot] = []
        for course in courses:
            occupied.append(
                TimeSlot(
                    start=course.start_time,
                    end=course.end_time,
                    type="course",
                    name=course.name,
                )
            )
        for task in tasks:
            occupied.append(
                TimeSlot(
                    start=task.start_time,
                    end=task.end_time,
                    type="task",
                    name=task.title,
                )
            )

        free_periods = compute_free_slots(
            occupied,
            min_duration_minutes=min_duration_minutes,
        )

        days.append(
            {
                "date": date_str,
                "weekday": weekday_names[weekday - 1],
                "free_periods": [
                    {
                        "start": slot.start,
                        "end": slot.end,
                        "duration_minutes": slot.duration_minutes,
                    }
                    for slot in free_periods
                ],
                "occupied": [
                    {
                        "start": slot.start,
                        "end": slot.end,
                        "type": slot.type,
                        "name": slot.name,
                    }
                    for slot in occupied
                ],
            }
        )
        current += timedelta(days=1)

    total_free_minutes = sum(
        slot["duration_minutes"]
        for day in days
        for slot in day["free_periods"]
    )
    total_slot_count = sum(len(day["free_periods"]) for day in days)
    return {
        "slots": days,
        "summary": (
            f"{start_date} 至 {end_date} 共 {total_slot_count} 个空闲段，"
            f"总计 {total_free_minutes // 60} 小时 {total_free_minutes % 60} 分钟"
        ),
    }


async def _create_study_plan(
    db: AsyncSession,
    user_id: str,
    exams: list,
    available_slots: dict,
    study_context: dict[str, Any] | None = None,
    strategy: str = "balanced",
    **kwargs,
) -> dict[str, Any]:
    tasks = await generate_study_plan(exams, available_slots, strategy, study_context=study_context)
    if not tasks:
        return {"error": "Failed to generate study plan. Please try again."}
    return {"tasks": tasks, "count": len(tasks)}


async def _create_work_plan(
    db: AsyncSession,
    user_id: str,
    work_items: list,
    available_slots: dict,
    work_context: dict[str, Any] | None = None,
    strategy: str = "staged",
    **kwargs,
) -> dict[str, Any]:
    tasks = await generate_work_plan(
        work_items,
        available_slots,
        strategy,
        work_context=work_context,
    )
    if not tasks:
        return {"error": "Failed to generate work plan. Please add deadline details or available time."}
    return {"tasks": tasks, "count": len(tasks)}


async def _list_tasks(
    db: AsyncSession,
    user_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    **kwargs,
) -> dict[str, Any]:
    query = select(Task).where(Task.user_id == user_id)
    if date_from:
        query = query.where(Task.scheduled_date >= date_from)
    if date_to:
        query = query.where(Task.scheduled_date <= date_to)
    query = query.order_by(Task.scheduled_date, Task.start_time)

    result = await db.execute(query)
    tasks = list(result.scalars().all())
    return {
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "scheduled_date": task.scheduled_date,
                "start_time": task.start_time,
                "end_time": task.end_time,
                "status": task.status,
            }
            for task in tasks
        ],
        "count": len(tasks),
    }


async def _find_task_conflict(
    db: AsyncSession,
    user_id: str,
    scheduled_date: str,
    start_time: str,
    end_time: str,
    exclude_task_id: str | None = None,
) -> Task | None:
    query = select(Task).where(
        Task.user_id == user_id,
        Task.scheduled_date == scheduled_date,
        Task.start_time < end_time,
        Task.end_time > start_time,
        Task.status != "skipped",
    )
    if exclude_task_id:
        query = query.where(Task.id != exclude_task_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


def _normalize_reminder_advance_minutes(value: Any) -> int | None:
    if value is None:
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("reminder_advance_minutes must be an integer") from exc
    if minutes < 0:
        raise ValueError("reminder_advance_minutes must be non-negative")
    return minutes


def _task_event_time(task: Task) -> str:
    return f"{task.scheduled_date}T{task.start_time}:00"


def _task_payload(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "scheduled_date": task.scheduled_date,
        "start_time": task.start_time,
        "end_time": task.end_time,
        "status": task.status,
    }


def _reminder_payload(reminder: Reminder) -> dict[str, Any]:
    return {
        "id": reminder.id,
        "target_type": reminder.target_type,
        "target_id": reminder.target_id,
        "remind_at": reminder.remind_at,
        "advance_minutes": reminder.advance_minutes,
        "status": reminder.status,
    }


async def _list_task_reminders(
    db: AsyncSession,
    user_id: str,
    task_id: str,
) -> list[Reminder]:
    result = await db.execute(
        select(Reminder).where(
            Reminder.user_id == user_id,
            Reminder.target_type == "task",
            Reminder.target_id == task_id,
        )
    )
    return list(result.scalars().all())


def _set_task_reminder_time(
    reminder: Reminder,
    task: Task,
    advance_minutes: int,
    user_id: str,
) -> None:
    fire_time = resolve_fire_time(_task_event_time(task), advance_minutes=advance_minutes)
    reminder.remind_at = fire_time.isoformat(timespec="seconds")
    reminder.advance_minutes = advance_minutes
    reminder.status = "pending"
    schedule_reminder_job(
        reminder_id=reminder.id,
        fire_time=fire_time,
        user_id=user_id,
    )


async def _sync_task_reminders(
    db: AsyncSession,
    user_id: str,
    task: Task,
    reminder_advance_minutes: int | None,
) -> list[Reminder]:
    reminders = await _list_task_reminders(db, user_id, task.id)
    if reminder_advance_minutes is None:
        for reminder in reminders:
            cancel_reminder_job(reminder.id)
            await db.delete(reminder)
        return []

    if not reminders:
        reminder = Reminder(
            user_id=user_id,
            target_type="task",
            target_id=task.id,
            remind_at="",
            advance_minutes=reminder_advance_minutes,
            status="pending",
        )
        db.add(reminder)
        await db.flush()
        reminders = [reminder]

    for reminder in reminders:
        _set_task_reminder_time(
            reminder=reminder,
            task=task,
            advance_minutes=reminder_advance_minutes,
            user_id=user_id,
        )
    return reminders


async def _reschedule_existing_task_reminders(
    db: AsyncSession,
    user_id: str,
    task: Task,
) -> list[Reminder]:
    reminders = await _list_task_reminders(db, user_id, task.id)
    for reminder in reminders:
        _set_task_reminder_time(
            reminder=reminder,
            task=task,
            advance_minutes=reminder.advance_minutes,
            user_id=user_id,
        )
    return reminders


async def _create_task(
    db: AsyncSession,
    user_id: str,
    title: str,
    scheduled_date: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    reminder_advance_minutes: int | None = None,
    _commit: bool = True,
    **kwargs,
) -> dict[str, Any]:
    reminder_minutes = _normalize_reminder_advance_minutes(reminder_advance_minutes)
    conflict = await _find_task_conflict(
        db,
        user_id,
        scheduled_date=scheduled_date,
        start_time=start_time,
        end_time=end_time,
    )
    if conflict is not None:
        return {
            "error": f"Time conflict with '{conflict.title}' ({conflict.start_time}-{conflict.end_time})"
        }

    task = Task(
        user_id=user_id,
        title=title,
        description=description,
        scheduled_date=scheduled_date,
        start_time=start_time,
        end_time=end_time,
    )
    db.add(task)
    await db.flush()
    reminders: list[Reminder] = []
    if reminder_minutes is not None:
        reminders = await _sync_task_reminders(db, user_id, task, reminder_minutes)
    if _commit:
        await db.commit()
        await db.refresh(task)
    task_summary = _task_payload(task)
    return {
        **task_summary,
        "status": "created",
        "task": task_summary,
        "reminders": [_reminder_payload(reminder) for reminder in reminders],
    }


async def _update_task(db: AsyncSession, user_id: str, task_id: str, _commit: bool = True, **kwargs) -> dict[str, Any]:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        if str(task_id).strip().lower() == "new":
            return {"error": "Task not found. Use create_task to create a new task first."}
        return {"error": "Task not found"}

    reminder_minutes_was_explicit = "reminder_advance_minutes" in kwargs
    reminder_minutes = _normalize_reminder_advance_minutes(
        kwargs.pop("reminder_advance_minutes", None)
    )
    new_date = kwargs.get("scheduled_date", task.scheduled_date)
    new_start = kwargs.get("start_time", task.start_time)
    new_end = kwargs.get("end_time", task.end_time)
    time_changed = any(key in kwargs for key in ("scheduled_date", "start_time", "end_time"))
    if time_changed:
        conflict = await _find_task_conflict(
            db,
            user_id,
            scheduled_date=new_date,
            start_time=new_start,
            end_time=new_end,
            exclude_task_id=task_id,
        )
        if conflict is not None:
            return {
                "error": f"Time conflict with '{conflict.title}' ({conflict.start_time}-{conflict.end_time})"
            }

    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)

    if reminder_minutes_was_explicit:
        reminders = await _sync_task_reminders(db, user_id, task, reminder_minutes)
    elif time_changed:
        reminders = await _reschedule_existing_task_reminders(db, user_id, task)
    else:
        reminders = await _list_task_reminders(db, user_id, task.id)

    if _commit:
        await db.commit()
        await db.refresh(task)
    task_summary = _task_payload(task)
    return {
        **task_summary,
        "status": "updated",
        "task": task_summary,
        "reminders": [_reminder_payload(reminder) for reminder in reminders],
    }


async def _complete_task(db: AsyncSession, user_id: str, task_id: str, _commit: bool = True, **kwargs) -> dict[str, Any]:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        return {"error": "Task not found"}

    task.status = "completed"
    if _commit:
        await db.commit()
    return {"id": task.id, "title": task.title, "status": "completed"}


async def _set_reminder(
    db: AsyncSession,
    user_id: str,
    target_type: str,
    target_id: str,
    advance_minutes: int = 15,
    **kwargs,
) -> dict[str, Any]:
    advance_minutes = _normalize_reminder_advance_minutes(advance_minutes)
    if advance_minutes is None:
        advance_minutes = 15
    if target_type == "course":
        result = await db.execute(
            select(Course).where(Course.id == target_id, Course.user_id == user_id)
        )
        target = result.scalar_one_or_none()
        if target is None:
            return {"error": "Course not found"}
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        occurrence = next_course_occurrence(
            target,
            user.current_semester_start if user else None,
        )
        if occurrence is None:
            return {"error": "Course has no upcoming active occurrence"}
        event_time = occurrence.isoformat(timespec="seconds")
    else:
        result = await db.execute(
            select(Task).where(Task.id == target_id, Task.user_id == user_id)
        )
        target = result.scalar_one_or_none()
        if target is None:
            return {"error": "Task not found"}
        reminders = await _sync_task_reminders(db, user_id, target, advance_minutes)
        await db.commit()
        reminder = reminders[0] if reminders else None
        if reminder is None:
            return {"status": "reminder_removed", "target_type": "task", "target_id": target_id}
        return {
            **_reminder_payload(reminder),
            "status": "reminder_set",
            "reminder": _reminder_payload(reminder),
        }

    fire_time = resolve_fire_time(event_time, advance_minutes=advance_minutes)
    remind_at = fire_time.isoformat(timespec="seconds")

    reminder = Reminder(
        user_id=user_id,
        target_type=target_type,
        target_id=target_id,
        remind_at=remind_at,
        advance_minutes=advance_minutes,
    )
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)

    schedule_reminder_job(
        reminder_id=reminder.id,
        fire_time=fire_time,
        user_id=user_id,
    )
    return {
        "id": reminder.id,
        "status": "reminder_set",
        "target_type": reminder.target_type,
        "target_id": reminder.target_id,
        "remind_at": remind_at,
        "advance_minutes": advance_minutes,
        "reminder": _reminder_payload(reminder),
    }




async def _list_reminders(db: AsyncSession, user_id: str, **kwargs) -> dict[str, Any]:
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.remind_at)
    )
    reminders = list(result.scalars().all())
    return {
        "reminders": [
            {
                "id": reminder.id,
                "target_type": reminder.target_type,
                "target_id": reminder.target_id,
                "remind_at": reminder.remind_at,
                "advance_minutes": reminder.advance_minutes,
                "status": reminder.status,
            }
            for reminder in reminders
        ],
        "count": len(reminders),
    }




async def _ask_user(
    db: AsyncSession | None = None,
    user_id: str | None = None,
    question: str = "",
    type: str = "review",
    **kwargs,
) -> dict[str, Any]:
    return {
        "action": "ask_user",
        "question": question,
        "type": type,
        "options": kwargs.get("options"),
        "data": kwargs.get("data"),
    }


async def _parse_schedule(
    db: AsyncSession,
    user_id: str,
    file_id: str,
    **kwargs,
) -> dict[str, Any]:
    return await _parse_cached_schedule(db, user_id, file_id, expected_kind="spreadsheet")


async def _parse_schedule_image(
    db: AsyncSession,
    user_id: str,
    file_id: str,
    **kwargs,
) -> dict[str, Any]:
    return await _parse_cached_schedule(db, user_id, file_id, expected_kind="image")


async def _parse_cached_schedule(
    db: AsyncSession,
    user_id: str,
    file_id: str,
    expected_kind: str,
) -> dict[str, Any]:
    cached = get_schedule_upload(user_id, file_id)
    if cached is None:
        return {"error": "Schedule upload not found"}
    if cached.kind != expected_kind:
        return {"error": f"Schedule upload kind mismatch: expected {expected_kind}, got {cached.kind}"}
    if cached.status in {"QUEUED", "PARSING"}:
        return {
            "status": "processing",
            "kind": cached.kind,
            "file_id": file_id,
            "progress": cached.progress,
            "message": "\u8bfe\u8868\u56fe\u7247\u4ecd\u5728\u89e3\u6790\u4e2d\uff0c\u8bf7\u7a0d\u5019\u518d\u8bd5\u3002",
        }
    if cached.status == "FAILED":
        return {
            "status": "failed",
            "kind": cached.kind,
            "file_id": file_id,
            "error": cached.error or "\u8bfe\u8868\u89e3\u6790\u5931\u8d25",
            "message": "\u8bfe\u8868\u56fe\u7247\u89e3\u6790\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20\u540e\u91cd\u8bd5\u3002",
        }
    if not cached.courses:
        update_schedule_upload_state(
            user_id,
            file_id,
            status="READY",
            missing_periods=[],
            missing_semester_fields=[],
            courses=[],
        )
        return {
            "status": "ready",
            "kind": cached.kind,
            "courses": [],
            "count": 0,
            "message": "没有从这张图片里识别到课程信息，请上传清晰的课表截图后重试。",
            "file_id": file_id,
        }
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    preferences = user.preferences if user else None
    schedule = _period_schedule_from_preferences(preferences)
    term_total_weeks = _term_total_weeks_from_preferences(preferences)
    missing_semester_fields: list[str] = []
    if user is None or user.current_semester_start is None:
        missing_semester_fields.append("semester_start_date")
    if term_total_weeks is None:
        missing_semester_fields.append("term_total_weeks")
    missing_periods: list[str] = []
    converted: list[dict[str, Any]] = []
    for course in cached.courses:
        course_data = dict(course)
        if "start_time" not in course_data or "end_time" not in course_data:
            raw_period = str(course_data.get("period") or "")
            try:
                period = normalize_period(raw_period)
            except ValueError:
                period = raw_period.strip()
            if not period:
                converted.append(course_data)
                continue
            times = convert_periods(period, schedule)
            if times is None:
                if period not in missing_periods:
                    missing_periods.append(period)
            else:
                course_data.update(times)
        if term_total_weeks is not None:
            _normalize_course_weeks(course_data, term_total_weeks)
        converted.append(course_data)
    if missing_periods or missing_semester_fields:
        update_schedule_upload_state(
            user_id,
            file_id,
            status="NEED_PERIOD_TIMES",
            missing_periods=missing_periods,
            missing_semester_fields=missing_semester_fields,
            courses=converted,
        )
        return {
            "status": "need_period_times",
            "kind": cached.kind,
            "courses": converted,
            "missing_periods": missing_periods,
            "missing_semester_fields": missing_semester_fields,
            "message": "\u8bfe\u8868\u8bc6\u522b\u5df2\u5b8c\u6210\uff0c\u4f46\u4ecd\u9700\u8865\u5145\u5b66\u671f\u5f00\u59cb\u65e5\u671f\u3001\u5b66\u671f\u603b\u5468\u6570\u548c/\u6216\u8282\u6b21\u65f6\u95f4\u3002\u8bf7\u4e00\u6b21\u6027\u8ffd\u95ee\u5e76\u8c03\u7528 save_period_times \u4fdd\u5b58\u3002",
            "file_id": file_id,
        }
    update_schedule_upload_state(
        user_id,
        file_id,
        status="READY",
        missing_periods=[],
        missing_semester_fields=[],
        courses=converted,
    )
    return {
        "status": "ready",
        "kind": cached.kind,
        "courses": converted,
        "count": len(converted),
        "message": "\u8bfe\u8868\u5df2\u89e3\u6790\uff0c\u8bf7\u901a\u8fc7 ask_user \u5411\u7528\u6237\u5c55\u793a\u8bc6\u522b\u7ed3\u679c\u5e76\u786e\u8ba4\u3002",
        "file_id": file_id,
    }
def _period_schedule_from_preferences(
    preferences: dict[str, Any] | None,
    term_id: str = "default",
) -> dict[str, dict[str, str]]:
    if not isinstance(preferences, dict):
        return {}
    templates = preferences.get("period_schedule_templates")
    if isinstance(templates, dict):
        schedule = templates.get(term_id)
        if isinstance(schedule, dict):
            return schedule
    schedule = preferences.get("period_schedule")
    if isinstance(schedule, dict):
        return schedule
    return {}


def _term_total_weeks_from_preferences(
    preferences: dict[str, Any] | None,
    term_id: str = "default",
) -> int | None:
    if not isinstance(preferences, dict):
        return None
    templates = preferences.get("term_total_weeks_templates")
    if isinstance(templates, dict):
        value = templates.get(term_id)
        if isinstance(value, int) and value > 0:
            return value
    for key in ("current_term_total_weeks", "term_total_weeks", "semester_total_weeks"):
        value = preferences.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _set_term_total_weeks(preferences: dict[str, Any], term_id: str, total_weeks: int) -> None:
    templates = dict(preferences.get("term_total_weeks_templates") or {})
    templates[term_id] = total_weeks
    preferences["term_total_weeks_templates"] = templates
    preferences["current_term_total_weeks"] = total_weeks


def _normalize_course_weeks(course_data: dict[str, Any], total_weeks: int) -> None:
    try:
        start = int(course_data.get("week_start", 1))
    except (TypeError, ValueError):
        start = 1
    try:
        end = int(course_data.get("week_end", total_weeks))
    except (TypeError, ValueError):
        end = total_weeks
    start = max(1, min(start, total_weeks))
    end = max(1, min(end, total_weeks))
    if end < start:
        end = start
    course_data["week_start"] = start
    course_data["week_end"] = end
    pattern = str(course_data.get("week_pattern") or "all").lower()
    if pattern not in {"all", "odd", "even"}:
        pattern = "all"
    course_data["week_pattern"] = pattern
    if course_data.get("week_text"):
        return
    if pattern == "odd":
        course_data["week_text"] = f"\u7b2c{start}-{end}\u5468(\u5355\u5468)"
    elif pattern == "even":
        course_data["week_text"] = f"\u7b2c{start}-{end}\u5468(\u53cc\u5468)"
    else:
        course_data["week_text"] = f"\u7b2c{start}-{end}\u5468"


async def _save_period_times(
    db: AsyncSession,
    user_id: str,
    file_id: str,
    entries: list[dict[str, str]] | None = None,
    semester_start_date: str | None = None,
    term_total_weeks: int | None = None,
    term_id: str = "default",
    **kwargs,
) -> dict[str, Any]:
    cached = get_schedule_upload(user_id, file_id)
    if cached is None:
        return {"error": "Schedule upload not found"}
    if cached.missing_periods is not None:
        required_periods = list(cached.missing_periods)
    else:
        required_periods = sorted(
            {
                str(course.get("period") or "").strip()
                for course in cached.courses
                if str(course.get("period") or "").strip()
            }
        )
    period_map: dict[str, dict[str, str]] = {}
    for entry in entries or []:
        try:
            period = normalize_period(str(entry.get("period") or ""))
            start_time, end_time = parse_time_range(str(entry.get("time") or ""))
        except ValueError as exc:
            return {"error": str(exc)}
        period_map[period] = {"start": start_time, "end": end_time}
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return {"error": "User not found"}
    preferences = dict(user.preferences or {})
    existing_schedule = dict(_period_schedule_from_preferences(preferences, term_id=term_id))
    resolved_schedule = dict(existing_schedule)
    resolved_schedule.update(period_map)
    existing_term_total_weeks = _term_total_weeks_from_preferences(preferences, term_id=term_id)
    resolved_term_total_weeks = term_total_weeks if term_total_weeks is not None else existing_term_total_weeks
    resolved_semester_start = user.current_semester_start
    if semester_start_date is not None:
        try:
            resolved_semester_start = date.fromisoformat(semester_start_date)
        except ValueError:
            return {"error": "semester_start_date must be in YYYY-MM-DD format"}
    if resolved_term_total_weeks is not None and resolved_term_total_weeks <= 0:
        return {"error": "term_total_weeks must be a positive integer"}
    missing_semester_fields: list[str] = []
    if resolved_semester_start is None:
        missing_semester_fields.append("semester_start_date")
    if resolved_term_total_weeks is None:
        missing_semester_fields.append("term_total_weeks")
    still_missing = [period for period in required_periods if period not in resolved_schedule]
    templates = dict(preferences.get("period_schedule_templates") or {})
    templates[term_id] = resolved_schedule
    preferences["period_schedule_templates"] = templates
    if term_id == "default":
        preferences["period_schedule"] = resolved_schedule
    if resolved_term_total_weeks is not None:
        _set_term_total_weeks(preferences, term_id, resolved_term_total_weeks)
    user.preferences = preferences
    user.current_semester_start = resolved_semester_start
    updated_courses: list[dict[str, Any]] = []
    for course in cached.courses:
        course_data = dict(course)
        if "start_time" not in course_data or "end_time" not in course_data:
            raw_period = str(course_data.get("period") or "")
            try:
                period = normalize_period(raw_period)
            except ValueError:
                period = raw_period.strip()
            times = convert_periods(period, resolved_schedule) if period else None
            if times is not None:
                course_data.update(times)
        if resolved_term_total_weeks is not None:
            _normalize_course_weeks(course_data, resolved_term_total_weeks)
        updated_courses.append(course_data)
    next_status = "READY"
    next_missing_periods: list[str] = []
    next_missing_semester_fields: list[str] = []
    if still_missing or missing_semester_fields:
        next_status = "NEED_PERIOD_TIMES"
        next_missing_periods = still_missing
        next_missing_semester_fields = missing_semester_fields

    update_schedule_upload_state(
        user_id,
        file_id,
        status=next_status,
        missing_periods=next_missing_periods,
        missing_semester_fields=next_missing_semester_fields,
        courses=updated_courses,
    )
    await db.commit()
    if still_missing or missing_semester_fields:
        return {
            "status": "need_period_times",
            "file_id": file_id,
            "courses": updated_courses,
            "missing_periods": still_missing,
            "missing_semester_fields": missing_semester_fields,
            "message": "\u4ecd\u6709\u4fe1\u606f\u672a\u8865\u5168\uff0c\u8bf7\u7ee7\u7eed\u8865\u5145\u3002",
        }
    return {
        "status": "ready",
        "file_id": file_id,
        "courses": updated_courses,
        "count": len(updated_courses),
        "semester_start_date": user.current_semester_start.isoformat() if user.current_semester_start else None,
        "term_total_weeks": resolved_term_total_weeks,
        "message": "\u8bfe\u8868\u8865\u5145\u4fe1\u606f\u5df2\u4fdd\u5b58\uff0c\u8bf7\u786e\u8ba4\u540e\u5bfc\u5165\u3002",
    }

async def _bulk_import_courses(
    db: AsyncSession,
    user_id: str,
    courses: list[dict[str, Any]],
    _commit: bool = True,
    **kwargs,
) -> dict[str, Any]:
    created: list[str] = []
    reminders_created = 0
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    semester_start = user.current_semester_start if user else None
    advance_minutes = _default_reminder_minutes_from_user(user)
    for course_data in courses:
        start_time = course_data.get("start_time")
        end_time = course_data.get("end_time")
        if not start_time or not end_time:
            period = course_data.get("period")
            await db.rollback()
            return {
                "error": f"课程 {course_data.get('name', '未命名课程')} 缺少具体时间，请先补充节次时间（period={period}）。"
            }

        normalized_course = _normalize_course_payload(course_data)
        course = Course(
            user_id=user_id,
            name=course_data["name"],
            teacher=course_data.get("teacher"),
            location=course_data.get("location"),
            weekday=course_data["weekday"],
            start_time=start_time,
            end_time=end_time,
            week_start=normalized_course["week_start"],
            week_end=normalized_course["week_end"],
            week_pattern=normalized_course["week_pattern"],
            week_text=normalized_course["week_text"],
        )
        db.add(course)
        await db.flush()

        occurrence = next_course_occurrence(course, semester_start)
        if occurrence is not None:
            fire_time = resolve_fire_time(
                occurrence.isoformat(timespec="seconds"),
                advance_minutes=advance_minutes,
            )
            reminder = Reminder(
                user_id=user_id,
                target_type="course",
                target_id=course.id,
                remind_at=fire_time.isoformat(timespec="seconds"),
                advance_minutes=advance_minutes,
            )
            db.add(reminder)
            await db.flush()

            schedule_reminder_job(
                reminder_id=reminder.id,
                fire_time=fire_time,
                user_id=user_id,
            )
            reminders_created += 1
        created.append(course_data["name"])

    if _commit:
        await db.commit()
    return {
        "status": "imported",
        "count": len(created),
        "courses": created,
        "reminders_created": reminders_created,
    }


async def _default_reminder_minutes(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    return _default_reminder_minutes_from_user(user)


def _default_reminder_minutes_from_user(user: User | None) -> int:
    preferences = user.preferences if user else None
    if isinstance(preferences, dict):
        value = preferences.get("default_reminder_minutes")
        if isinstance(value, int) and value > 0:
            return value
    return 15




async def _recall_memory(
    db: AsyncSession,
    user_id: str,
    query: str,
    **kwargs,
) -> dict[str, Any]:
    memories = await recall_memories(db, user_id, query)
    return {
        "memories": [
            {
                "id": memory.id,
                "category": memory.category,
                "content": memory.content,
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
            }
            for memory in memories
        ],
        "count": len(memories),
    }


async def _save_memory(
    db: AsyncSession,
    user_id: str,
    category: str,
    content: str,
    **kwargs,
) -> dict[str, Any]:
    memory = await create_memory(
        db=db,
        user_id=user_id,
        category=category,
        content=content,
    )
    return {
        "status": "saved",
        "id": memory.id,
        "message": f"已保存记忆：{content}",
    }


async def _delete_memory_handler(
    db: AsyncSession,
    user_id: str,
    memory_id: str,
    **kwargs,
) -> dict[str, Any]:
    deleted = await delete_memory_record(db, user_id, memory_id)
    if deleted:
        return {"status": "deleted", "message": "已删除这条记忆。"}
    return {"error": "Memory not found"}


TOOL_HANDLERS = {
    "list_courses": _list_courses,
    "add_course": _add_course,
    "update_course": _update_course,
    "delete_course": _delete_course,
    "get_free_slots": _get_free_slots,
    "create_study_plan": _create_study_plan,
    "create_work_plan": _create_work_plan,
    "list_tasks": _list_tasks,
    "create_task": _create_task,
    "update_task": _update_task,
    "complete_task": _complete_task,
    "set_reminder": _set_reminder,
    "list_reminders": _list_reminders,
    "ask_user": _ask_user,
    "parse_schedule": _parse_schedule,
    "parse_schedule_image": _parse_schedule_image,
    "save_period_times": _save_period_times,
    "bulk_import_courses": _bulk_import_courses,
    "recall_memory": _recall_memory,
    "save_memory": _save_memory,
    "delete_memory": _delete_memory_handler,
}
