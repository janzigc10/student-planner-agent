from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.reminder import Reminder
from app.models.user import User
from app.schemas.reminder import ReminderCreate, ReminderOut

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("/", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    body: ReminderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reminder = Reminder(user_id=user.id, **body.model_dump())
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.get("/", response_model=list[ReminderOut])
async def list_reminders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.remind_at))
    return result.scalars().all()


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await db.delete(reminder)
    await db.commit()