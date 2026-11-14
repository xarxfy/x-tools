"""two-factor login, history (events, metrics)

Revision ID: c3e4f5a6b7c8
Revises: b2d3f4a5c6e7
Create Date: 2026-11-15
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e4f5a6b7c8"
down_revision = "b2d3f4a5c6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("totp_secret", sa.Text(), nullable=True))
        batch.add_column(sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("totp_last_step", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("recovery_codes", sa.JSON(), nullable=False, server_default="[]"))
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_events_key", "events", ["key"])
    op.create_index("ix_events_started_at", "events", ["started_at"])
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("load", sa.Float(), nullable=True),
        sa.Column("mem", sa.Float(), nullable=True),
        sa.Column("disk", sa.Float(), nullable=True),
    )
    op.create_index("ix_metrics_source", "metrics", ["source"])
    op.create_index("ix_metrics_ts", "metrics", ["ts"])


def downgrade() -> None:
    op.drop_table("metrics")
    op.drop_table("events")
    with op.batch_alter_table("users") as batch:
        for col in ("recovery_codes", "totp_last_step", "totp_enabled", "totp_secret"):
            batch.drop_column(col)
