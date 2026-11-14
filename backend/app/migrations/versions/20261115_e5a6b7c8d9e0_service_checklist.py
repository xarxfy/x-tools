"""service setup checklist

Revision ID: e5a6b7c8d9e0
Revises: d4f5a6b7c8d9
Create Date: 2026-11-15
"""
import sqlalchemy as sa
from alembic import op

revision = "e5a6b7c8d9e0"
down_revision = "d4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("services") as batch:
        batch.add_column(sa.Column("checklist", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("services") as batch:
        batch.drop_column("checklist")
