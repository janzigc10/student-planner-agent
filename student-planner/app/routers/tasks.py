from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate

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
    task = Task(user_id=user.id, **body.model_dump())
    db.add(task)
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
    await db.delete(task)
    await db.commit()