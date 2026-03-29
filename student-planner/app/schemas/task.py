from typing import Optional

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    exam_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    scheduled_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    status: Optional[str] = Field(default=None, pattern=r"^(pending|completed|skipped)$")


class TaskOut(BaseModel):
    id: str
    user_id: str
    exam_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    scheduled_date: str
    start_time: str
    end_time: str
    status: str

    model_config = {"from_attributes": True}