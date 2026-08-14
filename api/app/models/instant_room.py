"""
Instant Rooms — lightweight, no-scheduling meeting rooms for day-to-day
conferencing, deliberately separate from Course/Section/ContentItem/
LiveSession. A LiveSession is always 1:1 with a scheduled training/webinar
content item and carries compliance/attendance-completion semantics
(SESSION_ATTENDANCE_COMPLETION_PCT, ContentProgress); an InstantRoom has
none of that — it's just "a room this person can start talking in," closer
to a personal meeting link than a course component. Keeping them fully
separate (not generalizing LiveSession to cover both) avoids stretching the
training-attendance model to cover a feature with no attendance-grading
concept at all.
"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class RoomAdmitMode(str, enum.Enum):
    automatic = "automatic"  # participant token grants full publish/subscribe immediately
    manual = "manual"        # participant joins hidden/muted until the host admits them


class InstantRoom(Base):
    __tablename__ = "instant_rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # LiveKit room slug — same pattern as LiveSession.room_name (models/live_session.py).
    room_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    admit_mode: Mapped[RoomAdmitMode] = mapped_column(
        SAEnum(RoomAdmitMode, name="roomadmitmode"), nullable=False, default=RoomAdmitMode.automatic
    )
    # A "standing" room is the owner's always-available personal room (like
    # a personal meeting link) rather than a one-off call — same LiveKit
    # room, just not deleted after everyone leaves. Distinguishes "my room"
    # from "the call I started five minutes ago" in the My Rooms list.
    is_standing_room: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_user_id])  # type: ignore[name-defined]
    members: Mapped[list["InstantRoomMember"]] = relationship(
        "InstantRoomMember", back_populates="room", cascade="all, delete-orphan"
    )
    participants: Mapped[list["InstantRoomParticipant"]] = relationship(
        "InstantRoomParticipant", back_populates="room", cascade="all, delete-orphan"
    )
    group_targets: Mapped[list["InstantRoomGroupTarget"]] = relationship(
        "InstantRoomGroupTarget", back_populates="room", cascade="all, delete-orphan"
    )


class InstantRoomMember(Base):
    """
    Invite list for a room — who can see/join it beyond the owner. Added by
    picking an existing user or by CPF (auto-provisioning an unregistered
    employee via services.provisioning.get_or_provision_by_cpf — the same
    shared helper used for course/group targeting, not a duplicate).
    """
    __tablename__ = "instant_room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_instant_room_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instant_rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    added_via_cpf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room: Mapped["InstantRoom"] = relationship("InstantRoom", back_populates="members")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]


class InstantRoomParticipant(Base):
    """
    Live/historical participant state for a room — deliberately NOT the same
    table as LiveSessionParticipant. Beyond join/leave timestamps, this also
    tracks live camera/mic/screen-share state (updated from LiveKit's
    track_published/track_unpublished webhook events — see
    routers/webhooks/livekit.py) so the admin Live Sessions dashboard can
    show who's on camera/screen-sharing right now. LiveSessionParticipant
    (models/live_session.py) gained the same three columns later, for the
    same reason — this comment originally said it hadn't, that's no longer
    true. `admitted` stays InstantRoom-only, since it exists only because
    InstantRoom supports RoomAdmitMode.manual (a training session
    LiveSession has no waiting-room concept at all — see
    LiveSession.waiting_room_enabled, which is a different, simpler bool).
    """
    __tablename__ = "instant_room_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instant_rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    admitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    camera_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mic_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    screen_sharing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    room: Mapped["InstantRoom"] = relationship("InstantRoom", back_populates="participants")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]


class InstantRoomGroupTarget(Base):
    """
    Targets a whole dynamic EmployeeGroup at an Instant Room — exactly the
    same shape/semantics as CourseTargetGroup (models/employee_group.py):
    additive on top of individually-added InstantRoomMember rows, resolved
    LIVE at access-check time (see routers/employee/rooms.py's
    _can_see_room), never materialized. Anyone currently matching ANY
    targeted group can see/join the room, same "additive OR across groups"
    principle used everywhere else a group can be attached to something.
    """
    __tablename__ = "instant_room_group_targets"
    __table_args__ = (
        UniqueConstraint("room_id", "group_id", name="uq_instant_room_group_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instant_rooms.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="CASCADE"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    room: Mapped["InstantRoom"] = relationship("InstantRoom", back_populates="group_targets")
    group: Mapped["EmployeeGroup"] = relationship("EmployeeGroup")  # type: ignore[name-defined]
