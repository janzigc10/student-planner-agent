from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.services.reminder_scheduler import cancel_reminder_job, resolve_fire_time, schedule_reminder_job

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def check_time_conflict(
    db: AsyncSession,
    user_id: str,
    date: str,
    start: str,
    end: str,
    exclude_id: str | None = None,
) -> Task | None:
    query = select(Task).where(
        Task.user_id == user_id,
        Task.scheduled_date == date,
        Task.start_time < end,
        Task.end_time > start,
        Task.status != "skipped",
    )
    if exclude_id:
        query = query.where(Task.id != exclude_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_task_reminders(
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


async def sync_task_reminders(
    db: AsyncSession,
    user_id: str,
    task: Task,
    reminder_advance_minutes: int | None,
) -> None:
    reminders = await list_task_reminders(db, user_id, task.id)

    if reminder_advance_minutes is None:
        for reminder in reminders:
            cancel_reminder_job(reminder.id)
            await db.delete(reminder)
        return

    event_time = f"{task.scheduled_date}T{task.start_time}:00"
    fire_time = resolve_fire_time(event_time, advance_minutes=reminder_advance_minutes)
    remind_at = fire_time.isoformat(timespec="seconds")

    if reminders:
        for reminder in reminders:
            reminder.remind_at = remind_at
            reminder.advance_minutes = reminder_advance_minutes
            reminder.status = "pending"
            schedule_reminder_job(
                reminder_id=reminder.id,
                fire_time=fire_time,
                user_id=user_id,
            )
        return

    reminder = Reminder(
        user_id=user_id,
        target_type="task",
        target_id=task.id,
        remind_at=remind_at,
        advance_minutes=reminder_advance_minutes,
        status="pending",
    )
    db.add(reminder)
    await db.flush()
    schedule_reminder_job(
        reminder_id=reminder.id,
        fire_time=fire_time,
        user_id=user_id,
    )


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conflict = await check_time_conflict(db, user.id, body.scheduled_date, body.start_time, body.end_time)
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Time conflict with '{conflict.title}' ({conflict.start_time}-{conflict.end_time})",
        )
    payload = body.model_dump(exclude={"reminder_advance_minutes"})
    task = Task(user_id=user.id, **payload)
    db.add(task)
    await db.flush()
    if body.reminder_advance_minutes is not None:
        await sync_task_reminders(db, user.id, task, body.reminder_advance_minutes)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/", response_model=list[TaskOut])
async def list_tasks(
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Task).where(Task.user_id == user.id)
    if date_from:
        query = query.where(Task.scheduled_date >= date_from)
    if date_to:
        query = query.where(Task.scheduled_date <= date_to)
    query = query.order_by(Task.scheduled_date, Task.start_time)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = body.model_dump(exclude_unset=True)
    reminder_advance_minutes = updates.pop("reminder_advance_minutes", None) if "reminder_advance_minutes" in updates else None
    reminder_minutes_was_explicit = "reminder_advance_minutes" in body.model_dump(exclude_unset=True)
    new_date = updates.get("scheduled_date", task.scheduled_date)
    new_start = updates.get("start_time", task.start_time)
    new_end = updates.get("end_time", task.end_time)

    if any(key in updates for key in ("scheduled_date", "start_time", "end_time")):
        conflict = await check_time_conflict(db, user.id, new_date, new_start, new_end, exclude_id=task_id)
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Time conflict with '{conflict.title}' ({conflict.start_time}-{conflict.end_time})",
            )

    for key, value in updates.items():
        setattr(task, key, value)

    if reminder_minutes_was_explicit:
        await sync_task_reminders(db, user.id, task, reminder_advance_minutes)
    elif any(key in updates for key in ("scheduled_date", "start_time")):
        reminders = await list_task_reminders(db, user.id, task_id)
        for reminder in reminders:
            event_time = f"{task.scheduled_date}T{task.start_time}:00"
            fire_time = resolve_fire_time(event_time, advance_minutes=reminder.advance_minutes)
            reminder.remind_at = fire_time.isoformat(timespec="seconds")
            reminder.status = "pending"
            schedule_reminder_job(
                reminder_id=reminder.id,
                fire_time=fire_time,
                user_id=user.id,
            )

    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    reminders = await list_task_reminders(db, user.id, task_id)
    for reminder in reminders:
        cancel_reminder_job(reminder.id)
        await db.delete(reminder)
    await db.delete(task)
    await db.commit()
