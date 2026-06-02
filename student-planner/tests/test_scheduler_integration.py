from datetime import datetime, timedelta

from app.services.reminder_scheduler import (
    cancel_reminder_job,
    get_scheduler,
    schedule_reminder_job,
)


def test_get_scheduler_returns_singleton():
    s1 = get_scheduler()
    s2 = get_scheduler()
    assert s1 is s2


def test_schedule_reminder_job_adds_job():
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start(paused=True)

    fire_time = datetime.now() + timedelta(hours=1)
    job = schedule_reminder_job(
        reminder_id="rem-123",
        fire_time=fire_time,
        user_id="user-456",
    )

    assert job is not None
    assert job.id == "reminder:rem-123"

    scheduler.remove_job(job.id)


def test_schedule_reminder_job_starts_scheduler_when_stopped():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)

    fire_time = datetime.now() + timedelta(hours=1)
    job = schedule_reminder_job(
        reminder_id="rem-start-1",
        fire_time=fire_time,
        user_id="user-456",
    )

    assert scheduler.running is True
    assert job.id == "reminder:rem-start-1"

    scheduler.remove_job(job.id)


def test_cancel_reminder_job():
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start(paused=True)

    fire_time = datetime.now() + timedelta(hours=1)
    schedule_reminder_job(
        reminder_id="rem-789",
        fire_time=fire_time,
        user_id="user-456",
    )

    cancel_reminder_job("rem-789")
    cancel_reminder_job("rem-789")
