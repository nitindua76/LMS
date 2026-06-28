"""Add storage_key to content_items for MinIO/local object storage.

Revision ID: 003
Revises: 002
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("storage_key", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_items", "storage_key")
