"""customer websites deployed from git

Revision ID: a7c8d9e0f1a2
Revises: f6b7c8d9e0f1
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "a7c8d9e0f1a2"
down_revision = "f6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("slug", sa.String(40), nullable=False, unique=True),
        sa.Column("customer_id", sa.String(12), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_id", sa.String(12), sa.ForeignKey("services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("repo_url", sa.String(300), nullable=False),
        sa.Column("branch", sa.String(100), nullable=False, server_default="main"),
        sa.Column("compose_file", sa.String(100), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("token", sa.Text(), nullable=False, server_default=""),
        sa.Column("env", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sites")
