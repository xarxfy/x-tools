"""Central tag list and colours for categories and groups; permission admin.organize

Revision ID: e7a8b9c0d1e2
Revises: d6f7a8b9c0d1
Create Date: 2026-11-26
"""
import json
import secrets

import sqlalchemy as sa
from alembic import op

revision = "e7a8b9c0d1e2"
down_revision = "d6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("color", sa.String(10), nullable=False, server_default="gray"),
    )
    for table in ("customer_categories", "server_groups"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("color", sa.String(10), nullable=False, server_default="gray"))
    # every tag that servers or customers already carry becomes an entry of the central list
    conn = op.get_bind()
    names: dict[str, str] = {}
    for table in ("agents", "customers"):
        for (raw,) in conn.execute(sa.text(f"SELECT tags FROM {table}")).fetchall():
            for tag in (json.loads(raw) if isinstance(raw, str) else raw) or []:
                names.setdefault(str(tag).lower(), str(tag))
    for table in ("agents", "customers"):  # one spelling per tag everywhere
        for rid, raw in conn.execute(sa.text(f"SELECT id, tags FROM {table}")).fetchall():
            tags = (json.loads(raw) if isinstance(raw, str) else raw) or []
            fixed = []
            for tag in tags:
                canon = names[str(tag).lower()]
                if canon not in fixed:
                    fixed.append(canon)
            if fixed != tags:
                conn.execute(sa.text(f"UPDATE {table} SET tags = :t WHERE id = :id"), {"t": json.dumps(fixed), "id": rid})
    for name in sorted(names.values(), key=str.lower):
        conn.execute(sa.text("INSERT INTO tags (id, name, color) VALUES (:id, :name, 'gray')"),
                     {"id": secrets.token_hex(6), "name": name})


def downgrade() -> None:
    raise NotImplementedError("downgrade is not supported")
