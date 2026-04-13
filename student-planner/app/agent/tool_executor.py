from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.study_planner import generate_study_plan
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
    compute_next_course_occurrence,
    resolve_fire_time,
    schedule_reminder_job,
)
from app.services.period_converter import DEFAULT_SCHEDULE, convert_periods
from app.services.schedule_upload_cache import get_schedule_upload


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    user_id: str,
) -> dict[str, Any]:
    """Dispatch a tool call to the appropriate handler."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await handler(db=db, user_id=user_id, **arguments)
    except Exception as exc:
        return {"error": str(exc)}


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
            }
            for course in courses
        ],
        "count": len(courses),
    }


async def _add_course(db: AsyncSession, user_id: str, **kwargs) -> dict[str, Any]:
    course = Course(user_id=user_id, **kwargs)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return {"id": course.id, "name": course.name, "status": "created"}


async def _delete_course(db: AsyncSession, user_id: str, course_id: str, **kwargs) -> dict[str, Any]:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    course = result.scalar_one_or_none()
    if course is None:
        return {"error": "Course not found"}

    await db.delete(course)
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
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    days: list[dict[str, Any]] = []

    current = start
    while current <= end:
        weekday = current.isoweekday()
        date_str = current.isoformat()

        course_result = await db.execute(
            select(Course).where(Course.user_id == user_id, Course.weekday == weekday)
        )
        courses = list(course_result.scalars().all())

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
    strategy: str = "balanced",
    **kwargs,
) -> dict[str, Any]:
    tasks = await generate_study_plan(exams, available_slots, strategy)
    if not tasks:
        return {"error": "Failed to generate study plan. Please try again."}
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


async def _update_task(db: AsyncSession, user_id: str, task_id: str, **kwargs) -> dict[str, Any]:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        return {"error": "Task not found"}

    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)

    await db.commit()
    await db.refresh(task)
    return {"id": task.id, "title": task.title, "status": "updated"}


async def _complete_task(db: AsyncSession, user_id: str, task_id: str, **kwargs) -> dict[str, Any]:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        return {"error": "Task not found"}

    task.status = "completed"
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
    if target_type == "course":
        result = await db.execute(
            select(Course).where(Course.id == target_id, Course.user_id == user_id)
        )
        target = result.scalar_one_or_none()
        if target is None:
            return {"error": "Course not found"}
        event_time = compute_next_course_occurrence(
            weekday=target.weekday,
            start_time=target.start_time,
        ).isoformat(timespec="seconds")
    else:
        result = await db.execute(
            select(Task).where(Task.id == target_id, Task.user_id == user_id)
        )
        target = result.scalar_one_or_none()
        if target is None:
            return {"error": "Task not found"}
        event_time = f"{target.scheduled_date}T{target.start_time}:00"

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
        "remind_at": remind_at,
        "advance_minutes": advance_minutes,
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
    type: str = "confirm",
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

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    schedule = _period_schedule_from_preferences(user.preferences if user else None)

    converted: list[dict[str, Any]] = []
    for course in cached.courses:
        course_data = dict(course)
        if "start_time" not in course_data or "end_time" not in course_data:
            period = course_data.get("period")
            times = convert_periods(str(period), schedule) if period else None
            if times is None:
                return {"error": f"Cannot convert period: {period}"}
            course_data.update(times)
        converted.append(course_data)

    return {
        "status": "ready",
        "kind": cached.kind,
        "courses": converted,
        "count": len(converted),
        "message": "课表已解析，请通过 ask_user 向用户展示识别结果并确认。",
        "file_id": file_id,
    }


def _period_schedule_from_preferences(preferences: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    if not preferences:
        return DEFAULT_SCHEDULE
    schedule = preferences.get("period_schedule")
    if isinstance(schedule, dict):
        return schedule
    return DEFAULT_SCHEDULE


async def _bulk_import_courses(
    db: AsyncSession,
    user_id: str,
    courses: list[dict[str, Any]],
    **kwargs,
) -> dict[str, Any]:
    created: list[str] = []
    reminders_created = 0
    advance_minutes = await _default_reminder_minutes(db, user_id)
    for course_data in courses:
        course = Course(
            user_id=user_id,
            name=course_data["name"],
            teacher=course_data.get("teacher"),
            location=course_data.get("location"),
            weekday=course_data["weekday"],
            start_time=course_data["start_time"],
            end_time=course_data["end_time"],
            week_start=course_data.get("week_start", 1),
            week_end=course_data.get("week_end", 16),
        )
        db.add(course)
        await db.flush()

        event_time = compute_next_course_occurrence(
            weekday=course.weekday,
            start_time=course.start_time,
        ).isoformat(timespec="seconds")
        fire_time = resolve_fire_time(event_time, advance_minutes=advance_minutes)
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
        created.append(course_data["name"])
        reminders_created += 1

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
    "delete_course": _delete_course,
    "get_free_slots": _get_free_slots,
    "create_study_plan": _create_study_plan,
    "list_tasks": _list_tasks,
    "update_task": _update_task,
    "complete_task": _complete_task,
    "set_reminder": _set_reminder,
    "list_reminders": _list_reminders,
    "ask_user": _ask_user,
    "parse_schedule": _parse_schedule,
    "parse_schedule_image": _parse_schedule_image,
    "bulk_import_courses": _bulk_import_courses,
    "recall_memory": _recall_memory,
    "save_memory": _save_memory,
    "delete_memory": _delete_memory_handler,
}
