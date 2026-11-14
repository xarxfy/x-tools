"""agent install options (encrypted)

Revision ID: f6b7c8d9e0f1
Revises: e5a6b7c8d9e0
Create Date: 2026-11-15
"""
import sqlalchemy as sa
from alembic import op

revision = "f6b7c8d9e0f1"
down_revision = "e5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("install_options", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.drop_column("install_options")
