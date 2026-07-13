"""Allow rescheduling a live session after it's cancelled/ended.

The original 007 migration made live_sessions.content_item_id UNIQUE,
mirroring how Quiz is a true 1:1 with Section. That assumption doesn't hold
for live sessions — unlike a quiz, a session is a point-in-time occurrence:
once cancelled or ended, an admin needs to schedule a fresh occurrence
(different time, different audience) for the same `meeting` content item,
while keeping the old occurrence's row around as an attendance/audit
record. Swaps the UNIQUE constraint for a plain index; application code
now always operates on the most recent row per content item (see
admin/sessions.py and employee/sessions.py `_get_session`/
`_get_enrollment_and_session`), only blocking a new POST when the most
recent existing session is still scheduled/live.

Revision ID: 008
Revises: 007
Create Date: 2026-07-10
"""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("live_sessions_content_item_id_key", "live_sessions", type_="unique")
    op.create_index(
        "ix_live_sessions_content_item_id", "live_sessions", ["content_item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_live_sessions_content_item_id", table_name="live_sessions")
    op.create_unique_constraint(
        "live_sessions_content_item_id_key", "live_sessions", ["content_item_id"]
    )
