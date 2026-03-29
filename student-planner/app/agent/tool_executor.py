from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.study_planner import generate_study_plan
from app.models.course import Course
from app.models.reminder import Reminder
from app.models.task import Task
from app.services.calendar import TimeSlot, compute_free_slots


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    user_id: str,
) -> dict[str, Any]:
    """Dispatch a tool call to the appropriate handler."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await handler(db=db, user_id=user_id, **arguments)
    except Exception as exc:
        return {"error": str(exc)}


async def _list_courses(db: AsyncSession, user_id: str, **kwargs) -> dict[str, Any]:
    result = await db.execute(select(Course).where(Course.user_id == user_id))
    courses = result.scalars().all()
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
    if not course:
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
        courses = course_result.scalars().all()

        task_result = await db.execute(
            select(Task).where(
                Task.user_id == user_id,
                Task.scheduled_date == date_str,
                Task.status != "skipped",
            )
        )
        tasks = task_result.scalars().all()

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
    tasks = result.scalars().all()
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
    if not task:
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
    if not task:
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
        if not target:
            return {"error": "Course not found"}
        remind_at = f"course:{target_id}:-{advance_minutes}min"
    else:
        result = await db.execute(
            select(Task).where(Task.id == target_id, Task.user_id == user_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            return {"error": "Task not found"}
        remind_at = f"{target.scheduled_date}T{target.start_time}:00"

    reminder = Reminder(
        user_id=user_id,
        target_type=target_type,
        target_id=target_id,
        remind_at=remind_at,
    )
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    return {"id": reminder.id, "status": "reminder_set", "remind_at": remind_at}


async def _list_reminders(db: AsyncSession, user_id: str, **kwargs) -> dict[str, Any]:
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.remind_at)
    )
    reminders = result.scalars().all()
    return {
        "reminders": [
            {
                "id": reminder.id,
                "target_type": reminder.target_type,
                "target_id": reminder.target_id,
                "remind_at": reminder.remind_at,
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

TOOL_HANDLERS = {
    "list_courses": _list_courses,
    "add_course": _add_course,
    "delete_course": _delete_course,
    "get_free_slots": _get_free_slots,
    "list_tasks": _list_tasks,
    "update_task": _update_task,
    "complete_task": _complete_task,
    "set_reminder": _set_reminder,
    "list_reminders": _list_reminders,
    "ask_user": _ask_user,
    "create_study_plan": _create_study_plan,
}