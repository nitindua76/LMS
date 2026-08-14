"""See migration 016 for the full rationale — this table backs the admin
Resource Monitor page (live gauges + historical chart of host CPU/memory
and LiveKit bandwidth/room/participant counts)."""
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class ResourceUsageSample(Base):
    __tablename__ = "resource_usage_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    host_cpu_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    host_memory_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    host_memory_used_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    host_memory_total_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    livekit_cpu_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    livekit_memory_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bandwidth_in_bytes_per_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bandwidth_out_bytes_per_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    active_room_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    active_participant_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
