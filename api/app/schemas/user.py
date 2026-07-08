from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.models.user import UserRole
from app.schemas.discipline import DisciplineRead
from app.schemas.level import LevelRead


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.employee
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None
    active: Optional[bool] = None


class UserResetPassword(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class UserRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    email: str
    role: UserRole
    active: bool
    force_password_change: bool
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None
    controller_id: Optional[int] = None
    discipline: Optional[DisciplineRead] = None
    level: Optional[LevelRead] = None
    created_at: datetime
    updated_at: datetime


class UserSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    email: str
    role: UserRole
    active: bool
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None
    created_at: datetime


# CSV import
class CSVImportRow(BaseModel):
    name: str
    email: str
    discipline: str
    level: str
    role: str = "employee"


class CSVRowResult(BaseModel):
    row: int
    email: str
    status: str
    error: Optional[str] = None
