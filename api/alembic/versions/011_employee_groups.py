"""Dynamic employee groups + course targeting via groups.

Adds employee_groups (admin-defined, rule-based), employee_group_rules
(AND-ed conditions per group over synced employee fields), and
course_target_groups (additive targeting, same shape as course_target_users).
Membership is never materialized — resolved live at query time (see
services/employee_groups.py) so new hires/transfers need zero admin upkeep.

Revision ID: 011
Revises: 010
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "employee_group_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("employee_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column(
            "operator",
            sa.Enum(
                "equals", "contains", "in_list", "is_direct_report_of", "is_in_subtree_of",
                name="ruleoperator",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(512), nullable=False),
    )
    op.create_index("ix_employee_group_rules_group_id", "employee_group_rules", ["group_id"])

    op.create_table(
        "course_target_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("employee_groups.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("course_id", "group_id", name="uq_course_target_group"),
    )


def downgrade() -> None:
    op.drop_table("course_target_groups")

    op.drop_index("ix_employee_group_rules_group_id", table_name="employee_group_rules")
    op.drop_table("employee_group_rules")
    sa.Enum(name="ruleoperator").drop(op.get_bind(), checkfirst=True)

    op.drop_table("employee_groups")
