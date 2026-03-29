from typing import Optional

from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    course_id: Optional[str] = None
    type: str = Field(default="exam", pattern=r"^(exam|assignment|other)$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: Optional[str] = None


class ExamUpdate(BaseModel):
    course_id: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern=r"^(exam|assignment|other)$")
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: Optional[str] = None


class ExamOut(BaseModel):
    id: str
    user_id: str
    course_id: Optional[str] = None
    type: str
    date: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}