"""heartbeat monitors for jobs

Revision ID: b8d9e0f1a2b3
Revises: a7c8d9e0f1a2
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "b8d9e0f1a2b3"
down_revision = "a7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "heartbeats",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token", sa.String(48), nullable=False, unique=True),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="1440"),
        sa.Column("grace_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(10), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("heartbeats")
