import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint,
    Index, func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class ProgressSource(str, enum.Enum):
    native = "native"
    scorm = "scorm"
    cmi5 = "cmi5"


class EnrollmentStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    expired = "expired"


class QuizAttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    submitted = "submitted"


class ReminderType(str, enum.Enum):
    start = "start"
    reminder_7d = "reminder_7d"
    reminder_3d = "reminder_3d"
    reminder_1d = "reminder_1d"
    overdue = "overdue"
    completion = "completion"


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollment"),
        Index("ix_enrollment_status_deadline", "status", "deadline_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(EnrollmentStatus, name="enrollmentstatus"),
        nullable=False,
        default=EnrollmentStatus.not_started,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_section_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    certificate_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="enrollments")  # type: ignore[name-defined]
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")  # type: ignore[name-defined]
    section_progress: Mapped[list["SectionProgress"]] = relationship(
        "SectionProgress", back_populates="enrollment", cascade="all, delete-orphan"
    )
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(
        "QuizAttempt", back_populates="enrollment"
    )
    sent_reminders: Mapped[list["SentReminder"]] = relationship(
        "SentReminder", back_populates="enrollment", cascade="all, delete-orphan"
    )


class SectionProgress(Base):
    __tablename__ = "section_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "section_id", name="uq_section_progress"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    content_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quiz_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[ProgressSource] = mapped_column(
        SAEnum(ProgressSource, name="progresssource"), nullable=False, default=ProgressSource.native
    )

    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="section_progress")
    section: Mapped["Section"] = relationship("Section", back_populates="section_progress")  # type: ignore[name-defined]


class ContentProgress(Base):
    """
    Per-(enrollment, content_item) native progress — one row per video/pdf item.

    This is the server-side source of truth behind the video heartbeat and the
    PDF/embedded-video dwell endpoints: `max_watched_seconds` only ever
    increases, and it's bounded by wall-clock time actually elapsed since
    `first_seen_at`/`last_heartbeat_at` rather than trusting whatever value the
    client posts. A section with multiple content items requires every item's
    `done` flag before the section itself is marked content_done — see
    app/services/content_progress.py.
    """
    __tablename__ = "content_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "content_item_id", name="uq_content_progress"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False
    )
    content_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_items.id", ondelete="RESTRICT"), nullable=False
    )
    max_watched_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    enrollment: Mapped["Enrollment"] = relationship("Enrollment")
    content_item: Mapped["ContentItem"] = relationship("ContentItem")  # type: ignore[name-defined]


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[QuizAttemptStatus] = mapped_column(
        SAEnum(QuizAttemptStatus, name="quizattemptstatus"), nullable=False
    )
    current_question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="attempts")  # type: ignore[name-defined]
    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="quiz_attempts")
    answers: Mapped[list["AttemptAnswer"]] = relationship(
        "AttemptAnswer", back_populates="attempt", cascade="all, delete-orphan"
    )


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False
    )
    served_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answer: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    time_taken_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    attempt: Mapped["QuizAttempt"] = relationship("QuizAttempt", back_populates="answers")
    question: Mapped["Question"] = relationship("Question", back_populates="attempt_answers")  # type: ignore[name-defined]


class SentReminder(Base):
    __tablename__ = "sent_reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False
    )
    reminder_type: Mapped[ReminderType] = mapped_column(
        SAEnum(ReminderType, name="remindertype"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="sent_reminders")
