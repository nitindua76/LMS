"""Add unique constraint on section_progress(enrollment_id, section_id).

Without this, a race between concurrent requests that both fall through the
"SELECT then INSERT" get-or-create path (e.g. the video heartbeat interval
firing alongside an onPause/onEnded trigger) can silently create duplicate
progress rows for the same enrollment+section — no error, just ambiguous data
picked up nondeterministically by whichever row a later query happens to load
first. This constraint turns that into a detectable, now-handled IntegrityError
instead (see app/standards/bridge.py::_get_or_create_sp).

Revision ID: 006
Revises: 005
Create Date: 2026-07-07
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_section_progress", "section_progress", ["enrollment_id", "section_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_section_progress", "section_progress", type_="unique")
