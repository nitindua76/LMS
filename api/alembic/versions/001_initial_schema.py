"""Initial schema — complete LMS data model

Revision ID: 001
Revises:
Create Date: 2026-06-26

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ──────────────────────────────────────────────────────────────
    userrole = postgresql.ENUM("admin", "employee", name="userrole", create_type=False)
    userrole.create(op.get_bind(), checkfirst=True)

    coursestatus = postgresql.ENUM("draft", "published", "archived", name="coursestatus", create_type=False)
    coursestatus.create(op.get_bind(), checkfirst=True)

    contenttype = postgresql.ENUM("video", "pdf", name="contenttype", create_type=False)
    contenttype.create(op.get_bind(), checkfirst=True)

    questiontype = postgresql.ENUM("mcq_single", "mcq_multi", "true_false", name="questiontype", create_type=False)
    questiontype.create(op.get_bind(), checkfirst=True)

    enrollmentstatus = postgresql.ENUM(
        "not_started", "in_progress", "completed", "failed", "expired",
        name="enrollmentstatus", create_type=False
    )
    enrollmentstatus.create(op.get_bind(), checkfirst=True)

    quizattemptstatus = postgresql.ENUM("in_progress", "submitted", name="quizattemptstatus", create_type=False)
    quizattemptstatus.create(op.get_bind(), checkfirst=True)

    remindertype = postgresql.ENUM(
        "start", "reminder_7d", "reminder_3d", "reminder_1d", "overdue", "completion",
        name="remindertype", create_type=False
    )
    remindertype.create(op.get_bind(), checkfirst=True)

    # ── disciplines ─────────────────────────────────────────────────────────────
    op.create_table(
        "disciplines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_discipline_name"),
    )

    # ── levels ───────────────────────────────────────────────────────────────────
    op.create_table(
        "levels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_level_code"),
    )

    # ── users ────────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(1024), nullable=False),
        sa.Column("discipline_id", sa.Integer,
                  sa.ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("level_id", sa.Integer,
                  sa.ForeignKey("levels.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("role", postgresql.ENUM("admin", "employee", name="userrole", create_type=False), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, default=True, server_default="true"),
        sa.Column("force_password_change", sa.Boolean, nullable=False, default=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── courses ──────────────────────────────────────────────────────────────────
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("intro", sa.Text, nullable=True),
        sa.Column("duration_days", sa.Integer, nullable=True),
        sa.Column("mandatory", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("passing_pct", sa.Integer, nullable=False, server_default="70"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("enroll_close_date", sa.Date, nullable=True),
        sa.Column("status", postgresql.ENUM("draft", "published", "archived", name="coursestatus", create_type=False), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── course_targets ───────────────────────────────────────────────────────────
    op.create_table(
        "course_targets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("course_id", sa.Integer,
                  sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discipline_id", sa.Integer,
                  sa.ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("level_id", sa.Integer,
                  sa.ForeignKey("levels.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("course_id", "discipline_id", "level_id", name="uq_course_target"),
    )

    # ── sections ─────────────────────────────────────────────────────────────────
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("course_id", sa.Integer,
                  sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.UniqueConstraint("course_id", "order_index", name="uq_section_order"),
    )

    # ── content_items ─────────────────────────────────────────────────────────────
    op.create_table(
        "content_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("section_id", sa.Integer,
                  sa.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("type", postgresql.ENUM("video", "pdf", name="contenttype", create_type=False), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("video_duration_sec", sa.Integer, nullable=True),
    )

    # ── quizzes ──────────────────────────────────────────────────────────────────
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("section_id", sa.Integer,
                  sa.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("passing_pct", sa.Integer, nullable=False, server_default="70"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
    )

    # ── questions ────────────────────────────────────────────────────────────────
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("quiz_id", sa.Integer,
                  sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("type", postgresql.ENUM("mcq_single", "mcq_multi", "true_false", name="questiontype", create_type=False), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("marks", sa.Integer, nullable=False, server_default="1"),
        sa.Column("timer_sec", sa.Integer, nullable=False, server_default="60"),
    )

    # ── options ──────────────────────────────────────────────────────────────────
    op.create_table(
        "options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("question_id", sa.Integer,
                  sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False, server_default="false"),
    )

    # ── enrollments ──────────────────────────────────────────────────────────────
    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("course_id", sa.Integer,
                  sa.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status",
                  postgresql.ENUM("not_started", "in_progress", "completed", "failed", "expired",
                                  name="enrollmentstatus", create_type=False),
                  nullable=False, server_default="not_started"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_section_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("certificate_url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "course_id", name="uq_enrollment"),
    )
    op.create_index("ix_enrollment_status_deadline", "enrollments", ["status", "deadline_at"])

    # ── section_progress ──────────────────────────────────────────────────────────
    op.create_table(
        "section_progress",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("enrollment_id", sa.Integer,
                  sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.Integer,
                  sa.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("content_done", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("quiz_passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── quiz_attempts ─────────────────────────────────────────────────────────────
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quiz_id", sa.Integer,
                  sa.ForeignKey("quizzes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("enrollment_id", sa.Integer,
                  sa.ForeignKey("enrollments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_no", sa.Integer, nullable=False),
        sa.Column("status",
                  postgresql.ENUM("in_progress", "submitted", name="quizattemptstatus", create_type=False), nullable=False),
        sa.Column("current_question_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("score_pct", sa.Integer, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── attempt_answers ───────────────────────────────────────────────────────────
    op.create_table(
        "attempt_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("attempt_id", sa.Integer,
                  sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer,
                  sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer", postgresql.JSONB, nullable=True),
        sa.Column("time_taken_sec", sa.Integer, nullable=True),
        sa.Column("timed_out", sa.Boolean, nullable=False, server_default="false"),
    )

    # ── sent_reminders ────────────────────────────────────────────────────────────
    op.create_table(
        "sent_reminders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("enrollment_id", sa.Integer,
                  sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reminder_type",
                  postgresql.ENUM("start", "reminder_7d", "reminder_3d", "reminder_1d", "overdue", "completion",
                                  name="remindertype", create_type=False), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── audit_logs ────────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=True),
        sa.Column("target_id", sa.String(255), nullable=True),
        sa.Column("detail", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("sent_reminders")
    op.drop_table("attempt_answers")
    op.drop_table("quiz_attempts")
    op.drop_table("section_progress")
    op.drop_table("enrollments")
    op.drop_table("options")
    op.drop_table("questions")
    op.drop_table("quizzes")
    op.drop_table("content_items")
    op.drop_table("sections")
    op.drop_table("course_targets")
    op.drop_table("courses")
    op.drop_table("users")
    op.drop_table("levels")
    op.drop_table("disciplines")

    for name in ("userrole", "coursestatus", "contenttype", "questiontype",
                 "enrollmentstatus", "quizattemptstatus", "remindertype"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
