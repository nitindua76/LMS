"""Instant Rooms: dynamic EmployeeGroup targeting.

instant_room_group_targets — exactly mirrors course_target_groups
(migration 011), just against instant_rooms instead of courses. Anyone
currently matching a targeted group can see/join the room, resolved live
at access-check time — no materialized membership, same principle as every
other group-targeting table in this schema.

Revision ID: 015
Revises: 014
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instant_room_group_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("instant_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("employee_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("room_id", "group_id", name="uq_instant_room_group_target"),
    )
    op.create_index("ix_instant_room_group_targets_room_id", "instant_room_group_targets", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_instant_room_group_targets_room_id", table_name="instant_room_group_targets")
    op.drop_table("instant_room_group_targets")
