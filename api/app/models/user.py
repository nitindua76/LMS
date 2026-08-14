import enum
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, Date, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    employee = "employee"


class AuthProvider(str, enum.Enum):
    # local: password_hash + argon2, unaffected by SSO reachability — kept
    # around deliberately as a break-glass path (see services/sso.py) so
    # login never has a hard dependency on an external system nobody here
    # controls the uptime of.
    local = "local"
    sso = "sso"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Nullable now: SSO-provisioned users never get a local password at all.
    # Only auth_provider=local accounts require this to be set (enforced in
    # services/auth.py / the admin user-create path, not at the DB level).
    password_hash: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
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

    # ── SSO / Employee API sync (see services/sso.py) ──────────────────────
    cpf: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True, index=True)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        SAEnum(AuthProvider, name="authprovider"), nullable=False, default=AuthProvider.local
    )
    # L1/L2/IC_HRER mirror controller_id's shape exactly (self-referential,
    # nullable, SET NULL on delete) — CONTROLLING from the Employee API maps
    # onto the pre-existing controller_id; these three are new tiers above it.
    l1_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    l2_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ic_hrer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Denormalized from the Employee API's GetFullDetails response — refreshed
    # on every login/sync (see upsert_user_from_employee_details). Purely
    # informational display fields; nothing else in the app reads these for
    # authorization decisions.
    designation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mobile: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    posting: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_upto: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_retired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Instant Rooms privilege (see models/instant_room.py) ────────────────
    # On by default per design — an explicit admin action is required to
    # take it away from someone, not to grant it.
    can_create_rooms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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
    l1: Mapped[Optional["User"]] = relationship("User", remote_side=[id], foreign_keys=[l1_id])
    l2: Mapped[Optional["User"]] = relationship("User", remote_side=[id], foreign_keys=[l2_id])
    ic_hrer: Mapped[Optional["User"]] = relationship("User", remote_side=[id], foreign_keys=[ic_hrer_id])
