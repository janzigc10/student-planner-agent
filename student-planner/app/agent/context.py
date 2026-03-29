from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.task import Task
from app.models.user import User

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


async def build_dynamic_context(user: User, db: AsyncSession) -> str:
    """Build the dynamic portion of the system prompt."""
    now = datetime.now(timezone.utc)
    today = now.date()
    weekday = today.isoweekday()

    parts: list[str] = []
    parts.append(f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}（{WEEKDAY_NAMES[weekday - 1]}）")

    if user.current_semester_start:
        delta = (today - user.current_semester_start).days
        week_num = delta // 7 + 1
        parts.append(f"当前学期：第{week_num}周")

    course_result = await db.execute(
        select(Course)
        .where(Course.user_id == user.id, Course.weekday == weekday)
        .order_by(Course.start_time)
    )
    courses = course_result.scalars().all()

    task_result = await db.execute(
        select(Task)
        .where(Task.user_id == user.id, Task.scheduled_date == today.isoformat())
        .order_by(Task.start_time)
    )
    tasks = task_result.scalars().all()

    parts.append("\n今天的日程：")
    if not courses and not tasks:
        parts.append("- 无安排")
    else:
        for course in courses:
            location = f" @ {course.location}" if course.location else ""
            parts.append(f"- {course.start_time}-{course.end_time} {course.name}{location}（课程）")
        for task in tasks:
            status_mark = "✓" if task.status == "completed" else "○"
            parts.append(f"- {task.start_time}-{task.end_time} {task.title}（{status_mark}）")

    preferences = user.preferences or {}
    if preferences:
        parts.append("\n用户偏好：")
        if "earliest_study" in preferences:
            parts.append(f"- 最早学习时间：{preferences['earliest_study']}")
        if "latest_study" in preferences:
            parts.append(f"- 最晚学习时间：{preferences['latest_study']}")
        if "lunch_break" in preferences:
            parts.append(f"- 午休：{preferences['lunch_break']}")
        if "min_slot_minutes" in preferences:
            parts.append(f"- 最短有效时段：{preferences['min_slot_minutes']}分钟")
        if "school_schedule" in preferences:
            parts.append("- 已配置作息时间表")

    return "\n".join(parts)