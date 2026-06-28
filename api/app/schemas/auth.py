from pydantic import BaseModel, EmailStr
from typing import Optional
from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    email: str
    role: UserRole
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None
    active: bool
    force_password_change: bool


class TokenPayload(BaseModel):
    sub: str
    jti: str
    role: str
    exp: int
    type: str
