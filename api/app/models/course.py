import enum
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Text, Boolean, Integer, DateTime, Date, ForeignKey,
    UniqueConstraint, func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class CourseStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class ContentType(str, enum.Enum):
    video = "video"
    pdf = "pdf"
    scorm = "scorm"
    cmi5 = "cmi5"


class QuestionType(str, enum.Enum):
    mcq_single = "mcq_single"
    mcq_multi = "mcq_multi"
    true_false = "true_false"


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    passing_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    enroll_close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[CourseStatus] = mapped_column(
        SAEnum(CourseStatus, name="coursestatus"), nullable=False, default=CourseStatus.draft
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    targets: Mapped[list["CourseTarget"]] = relationship(
        "CourseTarget", back_populates="course", cascade="all, delete-orphan"
    )
    sections: Mapped[list["Section"]] = relationship(
        "Section", back_populates="course", order_by="Section.order_index"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="course")  # type: ignore[name-defined]


class CourseTarget(Base):
    __tablename__ = "course_targets"
    __table_args__ = (
        UniqueConstraint("course_id", "discipline_id", "level_id", name="uq_course_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    discipline_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=False
    )
    level_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("levels.id", ondelete="RESTRICT"), nullable=False
    )

    course: Mapped["Course"] = relationship("Course", back_populates="targets")
    discipline: Mapped["Discipline"] = relationship("Discipline", back_populates="course_targets")  # type: ignore[name-defined]
    level: Mapped["Level"] = relationship("Level", back_populates="course_targets")  # type: ignore[name-defined]


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("course_id", "order_index", name="uq_section_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    course: Mapped["Course"] = relationship("Course", back_populates="sections")
    content_items: Mapped[list["ContentItem"]] = relationship(
        "ContentItem", back_populates="section", order_by="ContentItem.order_index",
        cascade="all, delete-orphan",
    )
    quiz: Mapped[Optional["Quiz"]] = relationship(
        "Quiz", back_populates="section", uselist=False, cascade="all, delete-orphan"
    )
    section_progress: Mapped[list["SectionProgress"]] = relationship("SectionProgress", back_populates="section")  # type: ignore[name-defined]


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[ContentType] = mapped_column(
        SAEnum(ContentType, name="contenttype"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)  # display label / external URL
    storage_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # MinIO/local object key; None = external
    video_duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    section: Mapped["Section"] = relationship("Section", back_populates="content_items")


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    passing_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    section: Mapped["Section"] = relationship("Section", back_populates="quiz")
    questions: Mapped[list["Question"]] = relationship(
        "Question", back_populates="quiz", order_by="Question.order_index",
        cascade="all, delete-orphan",
    )
    attempts: Mapped[list["QuizAttempt"]] = relationship("QuizAttempt", back_populates="quiz")  # type: ignore[name-defined]


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[QuestionType] = mapped_column(
        SAEnum(QuestionType, name="questiontype"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timer_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="questions")
    options: Mapped[list["Option"]] = relationship(
        "Option", back_populates="question", order_by="Option.order_index",
        cascade="all, delete-orphan",
    )
    attempt_answers: Mapped[list["AttemptAnswer"]] = relationship("AttemptAnswer", back_populates="question")  # type: ignore[name-defined]


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    question: Mapped["Question"] = relationship("Question", back_populates="options")
