"""IP addresses entered by hand; permission network.edit for operators

Revision ID: b4d5e6f7a8b9
Revises: a3c4d5e6f7a8
Create Date: 2026-11-23
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "b4d5e6f7a8b9"
down_revision = "a3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "network_entries",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("notes", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    conn = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.String), sa.column("permissions", sa.JSON))
    row = conn.execute(sa.select(roles.c.permissions).where(roles.c.id == "operator")).first()
    if row is not None:
        perms = json.loads(row[0]) if isinstance(row[0], str) else list(row[0] or [])
        if "network.edit" not in perms:
            conn.execute(roles.update().where(roles.c.id == "operator").values(permissions=sorted(perms + ["network.edit"])))


def downgrade() -> None:
    op.drop_table("network_entries")
