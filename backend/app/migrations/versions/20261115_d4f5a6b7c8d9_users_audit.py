"""disabled users, audit log

Revision ID: d4f5a6b7c8d9
Revises: c3e4f5a6b7c8
Create Date: 2026-11-15
"""
import sqlalchemy as sa
from alembic import op

revision = "d4f5a6b7c8d9"
down_revision = "c3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("disabled", sa.Boolean(), nullable=False, server_default="0"))
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("target", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_table("audit_log")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("disabled")
