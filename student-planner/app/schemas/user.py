from datetime import date
from typing import Any, Optional

from pydantic import BaseModel


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserUpdate(BaseModel):
    preferences: Optional[dict[str, Any]] = None
    current_semester_start: Optional[date] = None


class UserOut(BaseModel):
    id: str
    username: str
    preferences: Optional[dict[str, Any]] = None
    current_semester_start: Optional[date] = None

    model_config = {"from_attributes": True}
