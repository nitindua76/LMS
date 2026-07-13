"""
Dual schemas for questions/options — invariant #2:
  - Admin schemas include is_correct, marks, timer_sec
  - Employee schemas omit is_correct (never send answers to employees)
"""
from typing import Optional, List
from pydantic import BaseModel, field_validator, model_validator
from app.models.course import QuestionType


# ── Option schemas ─────────────────────────────────────────────────────────────

class OptionCreateAdmin(BaseModel):
    order_index: int
    text: str
    is_correct: bool = False

    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("option text cannot be empty")
        return v


class OptionUpdateAdmin(BaseModel):
    order_index: Optional[int] = None
    text: Optional[str] = None
    is_correct: Optional[bool] = None


class OptionReadAdmin(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    question_id: int
    order_index: int
    text: str
    is_correct: bool


class OptionReadEmployee(BaseModel):
    """Employee-facing: is_correct deliberately omitted."""
    model_config = {"from_attributes": True}

    id: int
    question_id: int
    order_index: int
    text: str


# ── Question schemas ───────────────────────────────────────────────────────────

def _validate_timer_sec(v: int) -> int:
    """0 is the sentinel for "no time limit" (avoids a nullable-column
    migration and the ambiguity a real None would have in a PATCH body,
    where None already means "don't change this field")."""
    if v != 0 and v < 5:
        raise ValueError("timer_sec must be 0 (no time limit) or >= 5")
    return v


def validate_question_options(question_type: QuestionType, options: list) -> None:
    """
    Shared by QuestionCreateAdmin's validator and the update_question router
    (which can't validate this at the schema level alone — a PATCH may
    change `options` without repeating `type`, so the effective type has to
    be resolved against the existing DB row first).
    """
    if question_type == QuestionType.true_false:
        if len(options) != 2:
            raise ValueError("true_false questions must have exactly 2 options")
    elif len(options) < 2:
        raise ValueError("questions must have at least 2 options")

    correct_count = sum(1 for o in options if o.is_correct)
    if question_type == QuestionType.mcq_single:
        if correct_count != 1:
            raise ValueError("mcq_single must have exactly 1 correct option")
    elif question_type == QuestionType.true_false:
        if correct_count != 1:
            raise ValueError("true_false must have exactly 1 correct option")
    elif question_type == QuestionType.mcq_multi:
        if correct_count < 1:
            raise ValueError("mcq_multi must have at least 1 correct option")


class QuestionCreateAdmin(BaseModel):
    order_index: int
    type: QuestionType
    text: str
    marks: int = 1
    timer_sec: int = 60
    options: List[OptionCreateAdmin]

    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question text cannot be empty")
        return v

    @field_validator("marks")
    @classmethod
    def marks_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("marks must be >= 1")
        return v

    @field_validator("timer_sec")
    @classmethod
    def timer_valid(cls, v: int) -> int:
        return _validate_timer_sec(v)

    @model_validator(mode="after")
    def validate_options(self) -> "QuestionCreateAdmin":
        validate_question_options(self.type, self.options)
        return self


class QuestionUpdateAdmin(BaseModel):
    order_index: Optional[int] = None
    type: Optional[QuestionType] = None
    text: Optional[str] = None
    marks: Optional[int] = None
    timer_sec: Optional[int] = None
    # When provided, replaces the question's options entirely (see
    # admin/quizzes.py::update_question) — validated there against the
    # effective type, since a PATCH may omit `type` and keep the existing one.
    options: Optional[List[OptionCreateAdmin]] = None

    @field_validator("timer_sec")
    @classmethod
    def timer_valid(cls, v: Optional[int]) -> Optional[int]:
        return v if v is None else _validate_timer_sec(v)


class QuestionReadAdmin(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    quiz_id: int
    order_index: int
    type: QuestionType
    text: str
    marks: int
    timer_sec: int
    options: List[OptionReadAdmin] = []


class QuestionReadEmployee(BaseModel):
    """Employee-facing: is_correct omitted from options."""
    model_config = {"from_attributes": True}

    id: int
    quiz_id: int
    order_index: int
    type: QuestionType
    text: str
    timer_sec: int
    options: List[OptionReadEmployee] = []


# ── Quiz schemas ───────────────────────────────────────────────────────────────

class QuizCreate(BaseModel):
    passing_pct: int = 70
    max_attempts: int = 3

    @field_validator("passing_pct")
    @classmethod
    def pct_range(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError("passing_pct must be 0–100")
        return v


class QuizUpdate(BaseModel):
    passing_pct: Optional[int] = None
    max_attempts: Optional[int] = None


class QuizReadAdmin(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    section_id: int
    passing_pct: int
    max_attempts: int
    questions: List[QuestionReadAdmin] = []


class QuizReadEmployee(BaseModel):
    """Employee-facing quiz — no correct answers."""
    model_config = {"from_attributes": True}

    id: int
    section_id: int
    passing_pct: int
    max_attempts: int
    questions: List[QuestionReadEmployee] = []
