from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class SystemSetting(Base):
    """
    Runtime-editable configuration, DB-first with an env-var fallback (see
    services/settings_service.py). Exists specifically so things like the
    SSO/Employee API endpoints and the Instant Rooms kill switch can be
    changed by an admin from the UI without a redeploy — everything else in
    the app (LiveKit, SMTP, storage) is still plain env vars in config.py;
    this table is only for the handful of settings that genuinely need to be
    admin-editable at runtime.
    """
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])  # type: ignore[name-defined]
