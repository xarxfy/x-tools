"""permission agents.manage replaces admin.agents (operators may manage agents)

Revision ID: f2b3c4d5e6f7
Revises: e1a2b3c4d5e6
Create Date: 2026-11-21
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "f2b3c4d5e6f7"
down_revision = "e1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _remap(conn, old: str, new: str, extra_for: str | None = None) -> None:
    roles = sa.table("roles", sa.column("id", sa.String), sa.column("permissions", sa.JSON))
    for rid, perms in conn.execute(sa.select(roles.c.id, roles.c.permissions)).all():
        perms = json.loads(perms) if isinstance(perms, str) else list(perms or [])
        changed = False
        if old in perms:
            perms = [new if p == old else p for p in perms]
            changed = True
        if extra_for and rid == extra_for and new not in perms:
            perms.append(new)
            changed = True
        if changed:
            conn.execute(roles.update().where(roles.c.id == rid).values(permissions=sorted(set(perms))))


def upgrade() -> None:
    _remap(op.get_bind(), "admin.agents", "agents.manage", extra_for="operator")


def downgrade() -> None:
    _remap(op.get_bind(), "agents.manage", "admin.agents")
