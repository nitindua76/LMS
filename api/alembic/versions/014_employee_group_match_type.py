"""Employee Groups: AND/OR match_type + more rule operators.

employee_groups gains match_type (enum 'all'|'any', default 'all') —
'all' preserves existing behavior (every rule must match, the original
AND-only semantics), 'any' lets an admin build an OR-across-rules group
(e.g. "Department A OR Department B OR reports to CPF X").

ruleoperator gains four more values: not_equals, not_contains, is_empty,
is_not_empty — Postgres enums need ALTER TYPE ... ADD VALUE for this,
which (unlike CREATE TYPE) cannot run inside the same transaction as other
DDL in some PG versions; run as its own statement with autocommit-safe
isolation via op.execute + explicit commit is unnecessary here since
alembic's env.py already runs migrations non-transactionally for enum
alters is NOT assumed — using the standard safe pattern instead.

Revision ID: 014
Revises: 013
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    match_type_enum = sa.Enum("all", "any", name="groupmatchtype")
    match_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "employee_groups",
        sa.Column("match_type", match_type_enum, nullable=False, server_default="all"),
    )

    # ALTER TYPE ... ADD VALUE must run outside the alembic-managed
    # transaction block on Postgres — op.execute with autocommit isolation.
    with op.get_context().autocommit_block():
        for value in ("not_equals", "not_contains", "is_empty", "is_not_empty"):
            op.execute(f"ALTER TYPE ruleoperator ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_column("employee_groups", "match_type")
    sa.Enum(name="groupmatchtype").drop(op.get_bind(), checkfirst=True)
    # Not reverting the ruleoperator enum values added above — Postgres has
    # no ALTER TYPE ... DROP VALUE, and any rows already using them would
    # need to be migrated off first. Acceptable one-way step, same as every
    # other enum-value addition in this codebase's migration history.
