import enum
import uuid as _uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class LaunchMode(str, enum.Enum):
    Normal = "Normal"
    Browse = "Browse"
    Review = "Review"


class Cmi5SessionState(str, enum.Enum):
    launched = "launched"
    initialized = "initialized"
    completed = "completed"
    passed = "passed"
    failed = "failed"
    terminated = "terminated"
    abandoned = "abandoned"


class Cmi5Registration(Base):
    __tablename__ = "cmi5_registrations"
    __table_args__ = (
        UniqueConstraint("user_id", "learning_package_id", name="uq_cmi5_reg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    learning_package_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_packages.id", ondelete="CASCADE"), nullable=False
    )
    registration: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, default=lambda: str(_uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    package: Mapped["LearningPackage"] = relationship(  # type: ignore[name-defined]
        "LearningPackage", back_populates="cmi5_registrations"
    )
    sessions: Mapped[list["Cmi5Session"]] = relationship(
        "Cmi5Session", back_populates="registration", cascade="all, delete-orphan"
    )


class Cmi5Session(Base):
    __tablename__ = "cmi5_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cmi5_registrations.id", ondelete="CASCADE"), nullable=False
    )
    au_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, default=lambda: str(_uuid.uuid4())
    )
    auth_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    launch_mode: Mapped[LaunchMode] = mapped_column(
        SAEnum(LaunchMode, name="launchmode"), nullable=False, default=LaunchMode.Normal
    )
    state: Mapped[Cmi5SessionState] = mapped_column(
        SAEnum(Cmi5SessionState, name="cmi5sessionstate"), nullable=False, default=Cmi5SessionState.launched
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    registration: Mapped["Cmi5Registration"] = relationship(
        "Cmi5Registration", back_populates="sessions"
    )
