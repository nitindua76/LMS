from typing import Optional
from pydantic import BaseModel
from app.schemas.discipline import DisciplineRead
from app.schemas.level import LevelRead


class TeamMemberSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    email: str
    discipline: Optional[DisciplineRead] = None
    level: Optional[LevelRead] = None


class SectionScore(BaseModel):
    section_id: int
    title: str
    order_index: int
    content_done: bool
    quiz_passed: Optional[bool] = None
    completed_at: Optional[str] = None
    has_quiz: bool
    best_score_pct: Optional[int] = None
    attempts_used: int = 0
    content_pct: Optional[float] = None


class TeamMemberCourseDetail(BaseModel):
    id: int
    title: str
    mandatory: bool
    state: str
    lock_reason: Optional[str] = None
    deadline_at: Optional[str] = None
    enrollment_id: Optional[int] = None
    started_at: Optional[str] = None
    sections: list[SectionScore]


class SetControllerRequest(BaseModel):
    controller_id: Optional[int] = None
