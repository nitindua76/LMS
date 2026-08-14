"""Live camera/mic/screen-share state on live_session_participants.

Mirrors instant_room_participants' camera_on/mic_on/screen_sharing columns
(migration 012) — LiveSession attendance rows previously only tracked
joined_at/left_at/duration_sec, so the admin Live Sessions dashboard could
show camera/screen-share counts for Instant Rooms but not for scheduled
training sessions (admin/rooms.py's _live_session_summary hardcoded these
to 0 with a comment explaining the gap). This closes that gap so "who
shared their screen, for how long" is available for both room kinds
consistently.

Revision ID: 013
Revises: 012
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "live_session_participants",
        sa.Column("camera_on", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "live_session_participants",
        sa.Column("mic_on", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "live_session_participants",
        sa.Column("screen_sharing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("live_session_participants", "screen_sharing")
    op.drop_column("live_session_participants", "mic_on")
    op.drop_column("live_session_participants", "camera_on")
