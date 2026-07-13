"""Course-level individual employee targeting.

Mirrors SessionAudienceRule.user_id (models/live_session.py) but for whole
courses: an admin can add specific employees to a course on top of its
normal CourseTarget (discipline+level) audience, without needing a
discipline/level match. Backs both a manual add-by-search UI and a CSV
bulk-import.

Revision ID: 009
Revises: 008
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_target_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("course_id", "user_id", name="uq_course_target_user"),
    )


def downgrade() -> None:
    op.drop_table("course_target_users")
