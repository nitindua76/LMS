import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class PackageFormat(str, enum.Enum):
    scorm_2004 = "scorm_2004"
    cmi5 = "cmi5"


class SequencingMode(str, enum.Enum):
    single_sco = "single_sco"
    simple_flow = "simple_flow"
    unsupported = "unsupported"


class MoveOn(str, enum.Enum):
    passed = "passed"
    completed = "completed"
    completed_and_passed = "completed_and_passed"
    completed_or_passed = "completed_or_passed"
    not_applicable = "not_applicable"


class LearningPackage(Base):
    __tablename__ = "learning_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    format: Mapped[PackageFormat] = mapped_column(
        SAEnum(PackageFormat, name="packageformat"), nullable=False
    )
    edition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    identifier: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    launch_href: Mapped[str] = mapped_column(Text, nullable=False)
    storage_root: Mapped[str] = mapped_column(Text, nullable=False)
    sequencing_mode: Mapped[SequencingMode] = mapped_column(
        SAEnum(SequencingMode, name="sequencingmode"), nullable=False, default=SequencingMode.single_sco
    )
    mastery_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    move_on: Mapped[Optional[MoveOn]] = mapped_column(
        SAEnum(MoveOn, name="moveon", create_type=False), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cmi_data: Mapped[list["ScormCmiData"]] = relationship(
        "ScormCmiData", back_populates="package", cascade="all, delete-orphan"
    )
    cmi5_registrations: Mapped[list["Cmi5Registration"]] = relationship(  # type: ignore[name-defined]
        "Cmi5Registration", back_populates="package", cascade="all, delete-orphan"
    )


class ScormCmiData(Base):
    __tablename__ = "scorm_cmi_data"
    __table_args__ = (
        UniqueConstraint("user_id", "learning_package_id", "sco_identifier", name="uq_scorm_cmi"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    learning_package_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_packages.id", ondelete="CASCADE"), nullable=False
    )
    sco_identifier: Mapped[str] = mapped_column(String(512), nullable=False)
    scorm_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    completion_status: Mapped[str] = mapped_column(String(50), nullable=False, default="not attempted")
    success_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    score_scaled: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    session_time: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_time: Mapped[str] = mapped_column(String(100), nullable=False, default="PT0S")
    suspend_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    entry: Mapped[str] = mapped_column(String(20), nullable=False, default="ab-initio")
    exit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    progress_measure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interactions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    objectives: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    package: Mapped["LearningPackage"] = relationship("LearningPackage", back_populates="cmi_data")
