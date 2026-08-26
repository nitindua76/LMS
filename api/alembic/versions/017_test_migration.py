"""Test migration — adds a nullable test_note column to users table.
This verifies the Alembic workflow between dev machines. Remove after testing.

Revision ID: 017
Revises: 016
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("test_note", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "test_note")
