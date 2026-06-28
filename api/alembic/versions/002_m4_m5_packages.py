"""M4/M5 — packages, SCORM CMI, cmi5, xAPI, progress source

Revision ID: 002
Revises: 001
Create Date: 2026-06-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extend existing contenttype enum (must be outside a transaction) ────────
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in Postgres.
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE contenttype ADD VALUE IF NOT EXISTS 'scorm'"))
        op.execute(sa.text("ALTER TYPE contenttype ADD VALUE IF NOT EXISTS 'cmi5'"))

    # ── New enum types ───────────────────────────────────────────────────────────
    progresssource = postgresql.ENUM("native", "scorm", "cmi5", name="progresssource", create_type=False)
    progresssource.create(op.get_bind(), checkfirst=True)

    packageformat = postgresql.ENUM("scorm_2004", "cmi5", name="packageformat", create_type=False)
    packageformat.create(op.get_bind(), checkfirst=True)

    sequencingmode = postgresql.ENUM("single_sco", "simple_flow", "unsupported", name="sequencingmode", create_type=False)
    sequencingmode.create(op.get_bind(), checkfirst=True)

    moveon = postgresql.ENUM(
        "passed", "completed", "completed_and_passed", "completed_or_passed", "not_applicable",
        name="moveon", create_type=False
    )
    moveon.create(op.get_bind(), checkfirst=True)

    launchmode = postgresql.ENUM("Normal", "Browse", "Review", name="launchmode", create_type=False)
    launchmode.create(op.get_bind(), checkfirst=True)

    cmi5sessionstate = postgresql.ENUM(
        "launched", "initialized", "completed", "passed", "failed", "terminated", "abandoned",
        name="cmi5sessionstate", create_type=False
    )
    cmi5sessionstate.create(op.get_bind(), checkfirst=True)

    # ── Add source column to section_progress ────────────────────────────────────
    op.add_column(
        "section_progress",
        sa.Column(
            "source",
            postgresql.ENUM("native", "scorm", "cmi5", name="progresssource", create_type=False),
            nullable=False,
            server_default="native",
        ),
    )

    # ── learning_packages ────────────────────────────────────────────────────────
    op.create_table(
        "learning_packages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content_item_id", sa.Integer,
                  sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", postgresql.ENUM("scorm_2004", "cmi5", name="packageformat", create_type=False), nullable=False),
        sa.Column("edition", sa.String(100), nullable=True),
        sa.Column("identifier", sa.String(512), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("version", sa.String(100), nullable=True),
        sa.Column("launch_href", sa.Text, nullable=False),
        sa.Column("storage_root", sa.Text, nullable=False),
        sa.Column("sequencing_mode",
                  postgresql.ENUM("single_sco", "simple_flow", "unsupported", name="sequencingmode", create_type=False),
                  nullable=False, server_default="single_sco"),
        sa.Column("mastery_score", sa.Float, nullable=True),
        sa.Column("move_on",
                  postgresql.ENUM("passed", "completed", "completed_and_passed", "completed_or_passed", "not_applicable",
                                  name="moveon", create_type=False),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── scorm_cmi_data ───────────────────────────────────────────────────────────
    op.create_table(
        "scorm_cmi_data",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("learning_package_id", sa.Integer,
                  sa.ForeignKey("learning_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sco_identifier", sa.String(512), nullable=False),
        sa.Column("scorm_session_id", sa.String(128), nullable=True),
        sa.Column("completion_status", sa.String(50), nullable=False, server_default="not attempted"),
        sa.Column("success_status", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("score_scaled", sa.Float, nullable=True),
        sa.Column("score_raw", sa.Float, nullable=True),
        sa.Column("score_min", sa.Float, nullable=True),
        sa.Column("score_max", sa.Float, nullable=True),
        sa.Column("session_time", sa.String(100), nullable=True),
        sa.Column("total_time", sa.String(100), nullable=False, server_default="PT0S"),
        sa.Column("suspend_data", sa.Text, nullable=True),
        sa.Column("location", sa.String(1000), nullable=True),
        sa.Column("entry", sa.String(20), nullable=False, server_default="ab-initio"),
        sa.Column("exit", sa.String(20), nullable=True),
        sa.Column("interactions", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("objectives", postgresql.JSONB, nullable=True, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "learning_package_id", "sco_identifier", name="uq_scorm_cmi"),
    )

    # ── cmi5_registrations ───────────────────────────────────────────────────────
    op.create_table(
        "cmi5_registrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("learning_package_id", sa.Integer,
                  sa.ForeignKey("learning_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("registration", postgresql.UUID(as_uuid=False), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "learning_package_id", name="uq_cmi5_reg"),
    )

    # ── cmi5_sessions ────────────────────────────────────────────────────────────
    op.create_table(
        "cmi5_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("registration_id", sa.Integer,
                  sa.ForeignKey("cmi5_registrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("au_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("auth_token", sa.String(512), nullable=True),
        sa.Column("launch_mode",
                  postgresql.ENUM("Normal", "Browse", "Review", name="launchmode", create_type=False),
                  nullable=False, server_default="Normal"),
        sa.Column("state",
                  postgresql.ENUM("launched","initialized","completed","passed","failed","terminated","abandoned",
                                  name="cmi5sessionstate", create_type=False),
                  nullable=False, server_default="launched"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── xapi_statements ──────────────────────────────────────────────────────────
    op.create_table(
        "xapi_statements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("statement_id", postgresql.UUID(as_uuid=False), nullable=False, unique=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor", postgresql.JSONB, nullable=False),
        sa.Column("verb", postgresql.JSONB, nullable=False),
        sa.Column("object", postgresql.JSONB, nullable=False),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("context", postgresql.JSONB, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forwarded", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lrs_response", postgresql.JSONB, nullable=True),
        sa.Column("enrollment_id", sa.Integer,
                  sa.ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_xapi_statements_enrollment", "xapi_statements", ["enrollment_id"])
    op.create_index("ix_xapi_statements_statement_id", "xapi_statements", ["statement_id"])


def downgrade() -> None:
    op.drop_table("xapi_statements")
    op.drop_table("cmi5_sessions")
    op.drop_table("cmi5_registrations")
    op.drop_table("scorm_cmi_data")
    op.drop_table("learning_packages")
    op.drop_column("section_progress", "source")

    for name in ("progresssource", "packageformat", "sequencingmode", "moveon", "launchmode", "cmi5sessionstate"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
