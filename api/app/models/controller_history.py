import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class ControllerAssignmentSource(str, enum.Enum):
    manual = "manual"
    api_sync = "api_sync"


class ControllerAssignmentHistory(Base):
    """
    Point-in-time record of who controlled whom. `users.controller_id` always
    holds the current assignment; this table is the audit trail behind it —
    one open row (effective_to = NULL) per user at a time.
    """
    __tablename__ = "controller_assignment_history"
    __table_args__ = (
        Index("ix_controller_history_user_open", "user_id", "effective_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    controller_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[ControllerAssignmentSource] = mapped_column(
        SAEnum(ControllerAssignmentSource, name="controllerassignmentsource"), nullable=False
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
    controller: Mapped[Optional["User"]] = relationship("User", foreign_keys=[controller_id])  # type: ignore[name-defined]
