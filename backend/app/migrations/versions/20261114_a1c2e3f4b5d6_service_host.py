"""service host for port checks

Revision ID: a1c2e3f4b5d6
Revises: 4db047c64968
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "a1c2e3f4b5d6"
down_revision = "4db047c64968"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("services") as batch:
        batch.add_column(sa.Column("host", sa.String(length=255), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("services") as batch:
        batch.drop_column("host")
