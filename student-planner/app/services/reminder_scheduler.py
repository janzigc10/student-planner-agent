"""Reminder scheduling and fire logic."""

import asyncio
from datetime import datetime, time, timedelta
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.database import async_session
from app.models.course import Course
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services.push_service import send_push

RETRY_DELAYS = [1, 5, 15]
REMINDER_SWEEP_INTERVAL_SECONDS = 15
_scheduler: AsyncIOScheduler | None = None


def _resolve_scheduler_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.new_event_loop()


def resolve_fire_time(event_time: str, advance_minutes: int = 15) -> datetime:
    dt = datetime.fromisoformat(event_time)
    return dt - timedelta(minutes=advance_minutes)


def compute_next_course_occurrence(
    weekday: int,
    start_time: str,
    now: datetime | None = None,
) -> datetime:
    current = now or datetime.now()
    start_clock = time.fromisoformat(start_time)
    days_ahead = weekday - current.isoweekday()
    if days_ahead < 0:
        days_ahead += 7
    elif days_ahead == 0 and current.time() >= start_clock:
        days_ahead = 7
    next_date = current.date() + timedelta(days=days_ahead)
    return datetime.combine(next_date, start_clock)


def build_push_payload(
    target_type: str,
    target_name: str,
    target_time: str,
    target_location: str | None = None,
) -> dict[str, str]:
    if target_type == "course":
        title = "课程提醒"
        location_part = f" @ {target_location}" if target_location else ""
        body = f"{target_time} {target_name}{location_part}"
    else:
        title = "任务提醒"
        body = f"该{target_name}了（{target_time}）"
    return {"title": title, "body": body}


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    loop = _resolve_scheduler_loop()
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(event_loop=loop)
    elif getattr(_scheduler, "_eventloop", None) is None or _scheduler._eventloop.is_closed():
        _scheduler._eventloop = loop
    elif not _scheduler.running:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not None and _scheduler._eventloop is not running_loop:
            _scheduler._eventloop = running_loop
    return _scheduler


def schedule_reminder_job(
    reminder_id: str,
    fire_time: datetime,
    user_id: str,
    attempt: int = 0,
) -> Any:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    if fire_time <= datetime.now():
        fire_time = datetime.now()
    job_id = f"reminder:{reminder_id}"
    if attempt > 0:
        job_id = f"reminder:{reminder_id}:retry{attempt}"
    return scheduler.add_job(
        "app.services.reminder_scheduler:fire_reminder",
        trigger="date",
        run_date=fire_time,
        id=job_id,
        replace_existing=True,
        kwargs={"reminder_id": reminder_id, "user_id": user_id, "attempt": attempt},
    )


def cancel_reminder_job(reminder_id: str) -> None:
    scheduler = get_scheduler()
    job_ids = [job.id for job in scheduler.get_jobs() if job.id.startswith(f"reminder:{reminder_id}")]
    if not job_ids:
        job_ids = [f"reminder:{reminder_id}"]
    for job_id in job_ids:
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass


async def fire_reminder(reminder_id: str, user_id: str, attempt: int = 0) -> None:
    async with async_session() as db:
        result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
        reminder = result.scalar_one_or_none()
        if reminder is None or reminder.status == "sent":
            return

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or user.push_subscription is None:
            reminder.status = "failed"
            await db.commit()
            return

        if reminder.target_type == "course":
            result = await db.execute(select(Course).where(Course.id == reminder.target_id))
            target = result.scalar_one_or_none()
            payload = build_push_payload(
                target_type="course",
                target_name=target.name if target else "未知课程",
                target_time=target.start_time if target else "",
                target_location=target.location if target else None,
            )
        else:
            result = await db.execute(select(Task).where(Task.id == reminder.target_id))
            target = result.scalar_one_or_none()
            payload = build_push_payload(
                target_type="task",
                target_name=target.title if target else "未知任务",
                target_time=f"{target.start_time}-{target.end_time}" if target else "",
            )

        push_result = send_push(
            subscription=user.push_subscription,
            title=payload["title"],
            body=payload["body"],
        )

        if push_result.ok:
            reminder.status = "sent"
            await db.commit()
            return

        if push_result.should_unsubscribe:
            user.push_subscription = None
            reminder.status = "failed"
            await db.commit()
            return

        if attempt < len(RETRY_DELAYS):
            retry_time = datetime.now() + timedelta(minutes=RETRY_DELAYS[attempt])
            schedule_reminder_job(
                reminder_id=reminder_id,
                fire_time=retry_time,
                user_id=user_id,
                attempt=attempt + 1,
            )
            await db.commit()
            return

        reminder.status = "failed"
        await db.commit()


async def reload_pending_reminders() -> int:
    count = 0
    async with async_session() as db:
        result = await db.execute(select(Reminder).where(Reminder.status == "pending"))
        reminders = list(result.scalars().all())

        now = datetime.now()
        for reminder in reminders:
            fire_time = datetime.fromisoformat(reminder.remind_at)
            if fire_time <= now:
                fire_time = now
            schedule_reminder_job(
                reminder_id=reminder.id,
                fire_time=fire_time,
                user_id=reminder.user_id,
            )
            count += 1
    return count


async def deliver_due_reminders(now: datetime | None = None) -> int:
    current = now or datetime.now()
    due: list[tuple[str, str]] = []

    async with async_session() as db:
        result = await db.execute(select(Reminder).where(Reminder.status == "pending"))
        reminders = list(result.scalars().all())
        for reminder in reminders:
            if datetime.fromisoformat(reminder.remind_at) <= current:
                due.append((reminder.id, reminder.user_id))

    for reminder_id, user_id in due:
        await fire_reminder(reminder_id=reminder_id, user_id=user_id)

    return len(due)


async def reminder_watch_loop(
    stop_event: asyncio.Event,
    interval_seconds: int = REMINDER_SWEEP_INTERVAL_SECONDS,
) -> None:
    while not stop_event.is_set():
        await deliver_due_reminders()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue
