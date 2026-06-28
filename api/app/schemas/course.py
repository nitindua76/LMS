from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, field_validator
from app.models.course import CourseStatus


class CourseTargetRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    discipline_id: int
    level_id: int


class CourseTargetCreate(BaseModel):
    discipline_id: int
    level_id: int


class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    intro: Optional[str] = None
    duration_days: Optional[int] = None
    mandatory: bool = False
    passing_pct: int = 70
    max_attempts: int = 3
    start_date: Optional[date] = None
    enroll_close_date: Optional[date] = None
    status: CourseStatus = CourseStatus.draft

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v

    @field_validator("passing_pct")
    @classmethod
    def pct_range(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError("passing_pct must be between 0 and 100")
        return v

    @field_validator("max_attempts")
    @classmethod
    def attempts_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_attempts must be at least 1")
        return v


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    intro: Optional[str] = None
    duration_days: Optional[int] = None
    mandatory: Optional[bool] = None
    passing_pct: Optional[int] = None
    max_attempts: Optional[int] = None
    start_date: Optional[date] = None
    enroll_close_date: Optional[date] = None
    status: Optional[CourseStatus] = None


class CourseRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    description: Optional[str] = None
    intro: Optional[str] = None
    duration_days: Optional[int] = None
    mandatory: bool
    passing_pct: int
    max_attempts: int
    start_date: Optional[date] = None
    enroll_close_date: Optional[date] = None
    status: CourseStatus
    created_at: datetime
    updated_at: datetime
    targets: List[CourseTargetRead] = []


class CourseSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    mandatory: bool
    status: CourseStatus
    duration_days: Optional[int] = None
    created_at: datetime
    targets: List[CourseTargetRead] = []
