"""Add controller_id to users and controller_assignment_history table.

Revision ID: 004
Revises: 003
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("controller_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_controller_id", "users", "users",
        ["controller_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_users_controller_id", "users", ["controller_id"])

    op.create_table(
        "controller_assignment_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("controller_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "source",
            sa.Enum("manual", "api_sync", name="controllerassignmentsource"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_controller_history_user_open", "controller_assignment_history",
        ["user_id", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index("ix_controller_history_user_open", table_name="controller_assignment_history")
    op.drop_table("controller_assignment_history")
    sa.Enum(name="controllerassignmentsource").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_users_controller_id", table_name="users")
    op.drop_constraint("fk_users_controller_id", "users", type_="foreignkey")
    op.drop_column("users", "controller_id")
