import uuid as _uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class XapiStatement(Base):
    __tablename__ = "xapi_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, unique=True,
        default=lambda: str(_uuid.uuid4())
    )
    actor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    verb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    object: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forwarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    forwarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lrs_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    enrollment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
