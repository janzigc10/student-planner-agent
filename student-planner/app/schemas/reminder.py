from pydantic import BaseModel, Field


class ReminderCreate(BaseModel):
    target_type: str = Field(pattern=r"^(course|task)$")
    target_id: str
    remind_at: str


class ReminderOut(BaseModel):
    id: str
    user_id: str
    target_type: str
    target_id: str
    remind_at: str
    status: str

    model_config = {"from_attributes": True}