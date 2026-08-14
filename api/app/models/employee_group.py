"""
Dynamic employee groups — an admin defines a group as a set of rules over
synced employee-profile fields (discipline, level, posting, designation,
hierarchy, etc.), not a fixed member list. Membership is resolved live at
query time (services/employee_groups.py) every time it's needed — there is
deliberately no materialized members table. A stored roster would go stale
the moment someone transfers departments or a new hire's account is
provisioned; since a group is just a filter over `users` columns, resolving
it live means new hires and transfers are picked up automatically with zero
admin upkeep, which is the entire point of this feature.
"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class RuleOperator(str, enum.Enum):
    equals = "equals"
    contains = "contains"
    in_list = "in_list"  # value is comma-separated
    # Hierarchy-aware operators — value is a CPF, resolved to a user at
    # evaluation time (see services/employee_groups.py).
    is_direct_report_of = "is_direct_report_of"
    is_in_subtree_of = "is_in_subtree_of"  # that CPF or anyone under them, any depth


class EmployeeGroup(Base):
    __tablename__ = "employee_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])  # type: ignore[name-defined]
    rules: Mapped[list["EmployeeGroupRule"]] = relationship(
        "EmployeeGroupRule", back_populates="group", cascade="all, delete-orphan"
    )
    course_targets: Mapped[list["CourseTargetGroup"]] = relationship(
        "CourseTargetGroup", back_populates="group", cascade="all, delete-orphan"
    )


class EmployeeGroupRule(Base):
    """
    One condition within a group. All rules belonging to the same group are
    ANDed together (see services/employee_groups.py::_group_query) — a group
    with zero rules matches nobody, deliberately, rather than everybody, so
    an incompletely-configured group can never silently target the entire
    organization.
    """
    __tablename__ = "employee_group_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="CASCADE"), nullable=False
    )
    # One of FIELD_MAP's keys in services/employee_groups.py (e.g.
    # "discipline_id", "posting", "designation", "gender") — not a DB FK,
    # since this is effectively a column-name reference resolved in Python.
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[RuleOperator] = mapped_column(
        SAEnum(RuleOperator, name="ruleoperator"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)

    group: Mapped["EmployeeGroup"] = relationship("EmployeeGroup", back_populates="rules")


class CourseTargetGroup(Base):
    """
    Targets a whole dynamic EmployeeGroup at a course — additive on top of
    CourseTarget/CourseTargetUser, same "additive OR" shape (see
    models/course.py's CourseTargetUser docstring). A user sees the course if
    they match ANY targeted group, and can match multiple groups without
    anything special happening — get_assigned_courses already unions every
    targeting path.
    """
    __tablename__ = "course_target_groups"
    __table_args__ = (
        UniqueConstraint("course_id", "group_id", name="uq_course_target_group"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employee_groups.id", ondelete="CASCADE"), nullable=False
    )

    course: Mapped["Course"] = relationship("Course")  # type: ignore[name-defined]
    group: Mapped["EmployeeGroup"] = relationship("EmployeeGroup", back_populates="course_targets")
