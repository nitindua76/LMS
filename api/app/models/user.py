import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    employee = "employee"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(1024), nullable=False)
    discipline_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=True
    )
    level_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("levels.id", ondelete="RESTRICT"), nullable=True
    )
    controller_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="userrole"), nullable=False, default=UserRole.employee
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    force_password_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    discipline: Mapped[Optional["Discipline"]] = relationship("Discipline", back_populates="users")  # type: ignore[name-defined]
    level: Mapped[Optional["Level"]] = relationship("Level", back_populates="users")  # type: ignore[name-defined]
    enrollments: Mapped[list["Enrollment"]] = relationship("Enrollment", back_populates="user")  # type: ignore[name-defined]
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id")  # type: ignore[name-defined]
    controller: Mapped[Optional["User"]] = relationship(
        "User", remote_side=[id], back_populates="subordinates", foreign_keys=[controller_id]
    )
    subordinates: Mapped[list["User"]] = relationship(
        "User", back_populates="controller", foreign_keys=[controller_id]
    )
