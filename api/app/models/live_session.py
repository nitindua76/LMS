import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint,
    CheckConstraint, func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class SessionMode(str, enum.Enum):
    meeting = "meeting"   # everyone can publish audio/video
    webinar = "webinar"   # only host/presenters publish; attendees subscribe-only


class SessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    live = "live"
    ended = "ended"
    cancelled = "cancelled"


class SessionParticipantRole(str, enum.Enum):
    host = "host"
    presenter = "presenter"
    attendee = "attendee"


class SessionReminderType(str, enum.Enum):
    starting_soon = "starting_soon"
    started = "started"


class LiveSession(Base):
    """
    1:1 companion to a ContentItem of type `meeting`, mirroring how Quiz is a
    1:1 companion to a Section. Holds everything needed to schedule and run
    a live video/audio session without touching the plain-file ContentItem
    fields (url/storage_key/video_duration_sec) that video/pdf/scorm use.
    """
    __tablename__ = "live_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Not unique: a content item can have several LiveSession rows over
    # time — one per scheduled occurrence. Once one is cancelled/ended, a
    # new one can be scheduled for the same content item; app code always
    # operates on the most recent row (see admin/sessions.py and
    # employee/sessions.py), and older rows stay as attendance history.
    content_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mode: Mapped[SessionMode] = mapped_column(
        SAEnum(SessionMode, name="sessionmode"), nullable=False, default=SessionMode.meeting
    )
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, name="sessionstatus"), nullable=False, default=SessionStatus.scheduled
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    join_before_start_min: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    host_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    waiting_room_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_participants: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    content_item: Mapped["ContentItem"] = relationship("ContentItem")  # type: ignore[name-defined]
    host: Mapped[Optional["User"]] = relationship("User", foreign_keys=[host_user_id])  # type: ignore[name-defined]
    audience_rules: Mapped[list["SessionAudienceRule"]] = relationship(
        "SessionAudienceRule", back_populates="live_session", cascade="all, delete-orphan"
    )
    participants: Mapped[list["LiveSessionParticipant"]] = relationship(
        "LiveSessionParticipant", back_populates="live_session", cascade="all, delete-orphan"
    )
    sent_reminders: Mapped[list["SentSessionReminder"]] = relationship(
        "SentSessionReminder", back_populates="live_session", cascade="all, delete-orphan"
    )


class SessionAudienceRule(Base):
    """
    Additive audience override for one LiveSession, layered on top of the
    course's normal CourseTarget (discipline+level) audience. A session with
    zero rules simply inherits the whole course audience; a row here adds
    exactly one discipline, one level, or one specific employee — without
    touching the course-level publish-gate logic in admin/courses.py.
    """
    __tablename__ = "session_audience_rules"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(discipline_id, level_id, user_id) = 1",
            name="ck_session_audience_rule_one_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    live_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False
    )
    discipline_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=True
    )
    level_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("levels.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    live_session: Mapped["LiveSession"] = relationship("LiveSession", back_populates="audience_rules")
    discipline: Mapped[Optional["Discipline"]] = relationship("Discipline")  # type: ignore[name-defined]
    level: Mapped[Optional["Level"]] = relationship("Level")  # type: ignore[name-defined]
    user: Mapped[Optional["User"]] = relationship("User")  # type: ignore[name-defined]


class LiveSessionParticipant(Base):
    """Attendance/compliance log, populated from LiveKit webhook events."""
    __tablename__ = "live_session_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    live_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[SessionParticipantRole] = mapped_column(
        SAEnum(SessionParticipantRole, name="sessionparticipantrole"),
        nullable=False, default=SessionParticipantRole.attendee,
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    live_session: Mapped["LiveSession"] = relationship("LiveSession", back_populates="participants")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]


class SentSessionReminder(Base):
    """
    Mirrors SentReminder/ReminderType (enrollment.py) but keyed by
    (live_session_id, user_id) since a session's audience is resolved
    dynamically from CourseTarget + SessionAudienceRule rather than a
    standing Enrollment row.
    """
    __tablename__ = "sent_session_reminders"
    __table_args__ = (
        UniqueConstraint(
            "live_session_id", "user_id", "reminder_type", name="uq_sent_session_reminder"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    live_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reminder_type: Mapped[SessionReminderType] = mapped_column(
        SAEnum(SessionReminderType, name="sessionremindertype"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    live_session: Mapped["LiveSession"] = relationship("LiveSession", back_populates="sent_reminders")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
