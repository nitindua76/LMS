"""Add content_progress table for per-content-item anti-spoof completion tracking.

Revision ID: 005
Revises: 004
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enrollment_id", sa.Integer(), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("max_watched_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("enrollment_id", "content_item_id", name="uq_content_progress"),
    )


def downgrade() -> None:
    op.drop_table("content_progress")
