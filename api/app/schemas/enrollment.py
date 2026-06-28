from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.enrollment import EnrollmentStatus


class EnrollmentRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    course_id: int
    status: EnrollmentStatus
    started_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    current_section_order: int
    certificate_url: Optional[str] = None
    created_at: datetime


class CourseState(BaseModel):
    """Computed state for an employee's course card."""
    course_id: int
    title: str
    mandatory: bool
    duration_days: Optional[int] = None
    state: str  # locked | available | not_started | in_progress | completed | failed | expired
    lock_reason: Optional[str] = None
    enrollment_id: Optional[int] = None
    deadline_at: Optional[datetime] = None
