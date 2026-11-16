"""notes for servers; longer notes for services

Revision ID: a3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-11-22
"""
import sqlalchemy as sa
from alembic import op

revision = "a3c4d5e6f7a8"
down_revision = "f2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("notes", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("services") as batch:
        batch.alter_column("notes", existing_type=sa.String(300), type_=sa.Text(), existing_nullable=False,
                           existing_server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("services") as batch:
        batch.alter_column("notes", existing_type=sa.Text(), type_=sa.String(300), existing_nullable=False)
    with op.batch_alter_table("agents") as batch:
        batch.drop_column("notes")
