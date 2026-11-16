"""Tickets and journal replace the customer tasks; customer links and tags; permission tickets.edit

Revision ID: d6f7a8b9c0d1
Revises: c5e6f7a8b9c0
Create Date: 2026-11-25
"""
import json
import secrets
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "d6f7a8b9c0d1"
down_revision = "c5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
        sa.Column("customer_id", sa.String(12), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("due", sa.Date, nullable=True),
        sa.Column("assignee_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_id", sa.String(12), sa.ForeignKey("services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", sa.String(12), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "journal",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("customer_id", sa.String(12), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("ticket_id", sa.String(12), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("kind", sa.String(10), nullable=False, server_default="note"),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("author", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.create_table(
        "customer_links",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("customer_id", sa.String(12), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("tags", sa.JSON, nullable=False, server_default="[]"))

    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    old = conn.execute(sa.text("SELECT id, customer_id, title, due, done, created_at FROM customer_tasks ORDER BY created_at")).fetchall()
    for n, (tid, cid, title, due, done, created) in enumerate(old, 1):
        conn.execute(sa.text(
            "INSERT INTO tickets (id, number, customer_id, title, description, status, priority, due, created_by, created_at, updated_at, closed_at) "
            "VALUES (:id, :n, :cid, :title, '', :status, 'normal', :due, '', :created, :created, :closed)"),
            {"id": tid, "n": n, "cid": cid, "title": title, "status": "done" if done else "open", "due": due,
             "created": created or now, "closed": (created or now) if done else None})
    op.drop_table("customer_tasks")

    roles = sa.table("roles", sa.column("id", sa.String), sa.column("permissions", sa.JSON))
    row = conn.execute(sa.select(roles.c.permissions).where(roles.c.id == "operator")).first()
    if row is not None:
        perms = json.loads(row[0]) if isinstance(row[0], str) else list(row[0] or [])
        if "tickets.edit" not in perms:
            conn.execute(roles.update().where(roles.c.id == "operator").values(permissions=sorted(perms + ["tickets.edit"])))


def downgrade() -> None:
    raise NotImplementedError("downgrade is not supported")
