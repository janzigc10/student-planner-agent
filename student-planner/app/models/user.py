import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    push_subscription: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    current_semester_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)