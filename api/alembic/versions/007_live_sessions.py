"""Live sessions — meeting content type, scheduling, audience, attendance.

Adds ContentType.meeting alongside video/pdf/scorm/cmi5, plus the tables
backing a scheduled live video/audio session: LiveSession (1:1 with a
ContentItem, mirrors how Quiz is 1:1 with a Section), SessionAudienceRule
(additive discipline/level/employee overrides on top of the course's normal
CourseTarget audience), LiveSessionParticipant (attendance log from LiveKit
webhooks), and SentSessionReminder (per-user reminder dedupe, mirroring
SentReminder but keyed by user since a session's audience is resolved
dynamically rather than via a standing Enrollment row).

Revision ID: 007
Revises: 006
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend existing contenttype enum (must be outside a transaction) ────────
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE contenttype ADD VALUE IF NOT EXISTS 'meeting'"))

    # ── New enum types ───────────────────────────────────────────────────────────
    sessionmode = postgresql.ENUM("meeting", "webinar", name="sessionmode", create_type=False)
    sessionmode.create(op.get_bind(), checkfirst=True)

    sessionstatus = postgresql.ENUM(
        "scheduled", "live", "ended", "cancelled", name="sessionstatus", create_type=False
    )
    sessionstatus.create(op.get_bind(), checkfirst=True)

    sessionparticipantrole = postgresql.ENUM(
        "host", "presenter", "attendee", name="sessionparticipantrole", create_type=False
    )
    sessionparticipantrole.create(op.get_bind(), checkfirst=True)

    sessionremindertype = postgresql.ENUM(
        "starting_soon", "started", name="sessionremindertype", create_type=False
    )
    sessionremindertype.create(op.get_bind(), checkfirst=True)

    # ── live_sessions ────────────────────────────────────────────────────────────
    op.create_table(
        "live_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_item_id", sa.Integer(),
                  sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("room_name", sa.String(255), nullable=False, unique=True),
        sa.Column("mode", sessionmode, nullable=False, server_default="meeting"),
        sa.Column("status", sessionstatus, nullable=False, server_default="scheduled"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("join_before_start_min", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("host_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("waiting_room_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_participants", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── session_audience_rules ───────────────────────────────────────────────────
    op.create_table(
        "session_audience_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("live_session_id", sa.Integer(),
                  sa.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discipline_id", sa.Integer(), sa.ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=True),
        sa.Column("level_id", sa.Integer(), sa.ForeignKey("levels.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(discipline_id, level_id, user_id) = 1",
            name="ck_session_audience_rule_one_target",
        ),
    )

    # ── live_session_participants ────────────────────────────────────────────────
    op.create_table(
        "live_session_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("live_session_id", sa.Integer(),
                  sa.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sessionparticipantrole, nullable=False, server_default="attendee"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=False, server_default="0"),
    )

    # ── sent_session_reminders ───────────────────────────────────────────────────
    op.create_table(
        "sent_session_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("live_session_id", sa.Integer(),
                  sa.ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reminder_type", sessionremindertype, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("live_session_id", "user_id", "reminder_type", name="uq_sent_session_reminder"),
    )


def downgrade() -> None:
    op.drop_table("sent_session_reminders")
    op.drop_table("live_session_participants")
    op.drop_table("session_audience_rules")
    op.drop_table("live_sessions")

    sa.Enum(name="sessionremindertype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sessionparticipantrole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sessionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sessionmode").drop(op.get_bind(), checkfirst=True)
    # Note: Postgres cannot remove a value from an existing enum type (contenttype),
    # so downgrade does not attempt to revert the 'meeting' addition.
