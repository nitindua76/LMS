"""SSO/CPF auth support, Employee API sync fields, and system_settings.

Adds `cpf` as an alternate login identifier alongside email, `auth_provider`
to distinguish local-password accounts (kept as a break-glass fallback) from
SSO-authenticated ones, l1/l2/ic_hrer as additional hierarchy tiers above the
existing controller_id, a set of denormalized fields refreshed from the
Employee API on each sync, and `can_create_rooms` for the Instant Rooms
per-user privilege. `password_hash` becomes nullable since SSO-provisioned
users never get a local password.

Also adds `system_settings`, a small DB-first/env-fallback key-value table
for the handful of settings (SSO/Employee API endpoints, Instant Rooms kill
switch) that need to be admin-editable at runtime without a redeploy.

Revision ID: 010
Revises: 009
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(1024), nullable=True)

    op.add_column("users", sa.Column("cpf", sa.String(32), nullable=True))
    op.create_unique_constraint("uq_users_cpf", "users", ["cpf"])
    op.create_index("ix_users_cpf", "users", ["cpf"])

    # Unlike a column added inside op.create_table(), ADD COLUMN on an
    # existing table does not implicitly CREATE TYPE for a native enum —
    # has to be created explicitly first or Postgres errors with
    # "type does not exist".
    authprovider_enum = sa.Enum("local", "sso", name="authprovider")
    authprovider_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            authprovider_enum,
            nullable=False,
            server_default="local",
        ),
    )

    op.add_column("users", sa.Column("l1_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("l2_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("ic_hrer_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_l1_id", "users", "users", ["l1_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_users_l2_id", "users", "users", ["l2_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_users_ic_hrer_id", "users", "users", ["ic_hrer_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_users_l1_id", "users", ["l1_id"])
    op.create_index("ix_users_l2_id", "users", ["l2_id"])
    op.create_index("ix_users_ic_hrer_id", "users", ["ic_hrer_id"])

    op.add_column("users", sa.Column("designation", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("mobile", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("posting", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("location", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(16), nullable=True))
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("valid_upto", sa.Date(), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_retired", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "users",
        sa.Column("can_create_rooms", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("system_settings")

    op.drop_column("users", "can_create_rooms")

    op.drop_column("users", "last_synced_at")
    op.drop_column("users", "is_retired")
    op.drop_column("users", "valid_upto")
    op.drop_column("users", "birth_date")
    op.drop_column("users", "gender")
    op.drop_column("users", "location")
    op.drop_column("users", "posting")
    op.drop_column("users", "mobile")
    op.drop_column("users", "designation")

    op.drop_index("ix_users_ic_hrer_id", table_name="users")
    op.drop_index("ix_users_l2_id", table_name="users")
    op.drop_index("ix_users_l1_id", table_name="users")
    op.drop_constraint("fk_users_ic_hrer_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_l2_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_l1_id", "users", type_="foreignkey")
    op.drop_column("users", "ic_hrer_id")
    op.drop_column("users", "l2_id")
    op.drop_column("users", "l1_id")

    op.drop_column("users", "auth_provider")
    sa.Enum(name="authprovider").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_users_cpf", table_name="users")
    op.drop_constraint("uq_users_cpf", "users", type_="unique")
    op.drop_column("users", "cpf")

    op.alter_column("users", "password_hash", existing_type=sa.String(1024), nullable=False)
