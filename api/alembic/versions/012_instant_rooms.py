"""Instant Rooms — day-to-day meeting rooms, separate from LiveSession.

instant_rooms: owner_user_id, name, room_name (LiveKit slug, unique),
admit_mode (automatic|manual), is_standing_room, active/ended_at.
instant_room_members: invite list, CPF-addable.
instant_room_participants: attendance + live camera/mic/screen-share state
(distinct from LiveSessionParticipant — no attendance-completion semantics
here, but needs live media state for the admin dashboard).

Revision ID: 012
Revises: 011
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instant_rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("room_name", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "admit_mode",
            sa.Enum("automatic", "manual", name="roomadmitmode"),
            nullable=False,
            server_default="automatic",
        ),
        sa.Column("is_standing_room", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_instant_rooms_owner_user_id", "instant_rooms", ["owner_user_id"])

    op.create_table(
        "instant_room_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("instant_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("added_via_cpf", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("room_id", "user_id", name="uq_instant_room_member"),
    )

    op.create_table(
        "instant_room_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("instant_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("admitted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("camera_on", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mic_on", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("screen_sharing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_instant_room_participants_room_id", "instant_room_participants", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_instant_room_participants_room_id", table_name="instant_room_participants")
    op.drop_table("instant_room_participants")

    op.drop_table("instant_room_members")

    op.drop_index("ix_instant_rooms_owner_user_id", table_name="instant_rooms")
    op.drop_table("instant_rooms")
    sa.Enum(name="roomadmitmode").drop(op.get_bind(), checkfirst=True)
