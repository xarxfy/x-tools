"""roles with free permissions

Revision ID: e1a2b3c4d5e6
Revises: d0f1a2b3c4d5
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "e1a2b3c4d5e6"
down_revision = "d0f1a2b3c4d5"
branch_labels = None
depends_on = None

# Frozen copy of the built-in roles at the time of this migration (later changes belong in new migrations).
ALL = ["services.edit", "credentials.manage", "customers.edit", "sites.deploy", "jobs.edit", "alerts.pause",
       "docker.control", "proxmox.control", "servers.control", "servers.manage", "servers.organize",
       "cloudflare.edit", "admin.users", "admin.roles", "admin.agents", "admin.settings", "admin.backup",
       "admin.audit"]
OPERATOR = [p for p in ALL if not p.startswith("admin.") and p != "servers.manage"]


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False, unique=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.bulk_insert(roles, [
        {"id": "viewer", "name": "Viewer", "permissions": [], "builtin": True},
        {"id": "operator", "name": "Operator", "permissions": OPERATOR, "builtin": True},
        {"id": "admin", "name": "Administrator", "permissions": ALL, "builtin": True},
    ])


def downgrade() -> None:
    op.drop_table("roles")
