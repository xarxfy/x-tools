"""agent kind (proxmox / docker)

Revision ID: b2d3f4a5c6e7
Revises: a1c2e3f4b5d6
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "b2d3f4a5c6e7"
down_revision = "a1c2e3f4b5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=20), nullable=False, server_default="docker"))
    # Existing agents that already report Proxmox data are Proxmox hosts.
    op.execute("UPDATE agents SET kind = 'proxmox' "
               "WHERE last_report IS NOT NULL AND json_extract(last_report, '$.proxmox') IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.drop_column("kind")
