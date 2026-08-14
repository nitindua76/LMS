"""Resource usage samples — periodic snapshots of host CPU/memory and
LiveKit bandwidth/room/participant counts, for the admin Resource Monitor
page's live gauges + historical chart.

One row per sampling tick (see services/resource_monitor.py's scheduler,
~60s interval) — small enough that this table can be kept indefinitely at
this deployment's scale (single host, a handful of concurrent rooms), but
callers should still page/limit queries rather than assuming it stays
small forever.

Revision ID: 016
Revises: 015
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_usage_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sampled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Host-level (Docker Desktop VM / node) CPU+memory, via psutil in
        # the api container — see resource_monitor.py's module docstring
        # for why this is host-wide, not per-container, on this platform.
        sa.Column("host_cpu_pct", sa.Float(), nullable=True),
        sa.Column("host_memory_pct", sa.Float(), nullable=True),
        sa.Column("host_memory_used_mb", sa.Float(), nullable=True),
        sa.Column("host_memory_total_mb", sa.Float(), nullable=True),
        # LiveKit server process (its own CPU/memory, via Prometheus'
        # standard process_cpu_seconds_total / process_resident_memory_bytes).
        sa.Column("livekit_cpu_pct", sa.Float(), nullable=True),
        sa.Column("livekit_memory_mb", sa.Float(), nullable=True),
        # Bandwidth: bytes/sec, computed as a delta between consecutive
        # cumulative Prometheus counter samples (see resource_monitor.py).
        sa.Column("bandwidth_in_bytes_per_sec", sa.Float(), nullable=True),
        sa.Column("bandwidth_out_bytes_per_sec", sa.Float(), nullable=True),
        sa.Column("active_room_count", sa.Integer(), nullable=True),
        sa.Column("active_participant_count", sa.Integer(), nullable=True),
    )
    op.create_index("ix_resource_usage_samples_sampled_at", "resource_usage_samples", ["sampled_at"])


def downgrade() -> None:
    op.drop_index("ix_resource_usage_samples_sampled_at", table_name="resource_usage_samples")
    op.drop_table("resource_usage_samples")
