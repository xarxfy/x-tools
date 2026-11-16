"""Customers: several contacts, contract data, tasks, servers and jobs assigned to a customer

Revision ID: c5e6f7a8b9c0
Revises: b4d5e6f7a8b9
Create Date: 2026-11-24
"""
import json
import secrets

import sqlalchemy as sa
from alembic import op

revision = "c5e6f7a8b9c0"
down_revision = "b4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_contacts",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("customer_id", sa.String(12), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("role", sa.String(60), nullable=False, server_default=""),
        sa.Column("email", sa.String(120), nullable=False, server_default=""),
        sa.Column("phone", sa.String(40), nullable=False, server_default=""),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "customer_tasks",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("customer_id", sa.String(12), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due", sa.Date, nullable=True),
        sa.Column("done", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    conn = op.get_bind()
    # the single contact of before becomes the first contact person
    old = conn.execute(sa.text("SELECT id, contact, email, phone FROM customers")).fetchall()
    for cid, contact, email, phone in old:
        if (contact or email or phone):
            conn.execute(sa.text("INSERT INTO customer_contacts (id, customer_id, name, role, email, phone, position) "
                                 "VALUES (:id, :cid, :name, '', :email, :phone, 0)"),
                         {"id": secrets.token_hex(6), "cid": cid, "name": contact or email or phone,
                          "email": email or "", "phone": phone or ""})
    with op.batch_alter_table("customers") as batch:
        batch.drop_column("contact")
        batch.drop_column("email")
        batch.drop_column("phone")
        batch.add_column(sa.Column("contract_end", sa.Date, nullable=True))
        batch.add_column(sa.Column("notice_days", sa.Integer, nullable=True))
        batch.add_column(sa.Column("support_hours", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("response_time", sa.String(60), nullable=False, server_default=""))
    for table in ("agents", "heartbeats"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("customer_id", sa.String(12), nullable=True))
            batch.create_foreign_key(f"fk_{table}_customer", "customers", ["customer_id"], ["id"], ondelete="SET NULL")
    roles = sa.table("roles", sa.column("id", sa.String), sa.column("permissions", sa.JSON))
    row = conn.execute(sa.select(roles.c.permissions).where(roles.c.id == "operator")).first()
    if row is not None:
        perms = json.loads(row[0]) if isinstance(row[0], str) else list(row[0] or [])
        if "customers.contracts" not in perms:
            conn.execute(roles.update().where(roles.c.id == "operator").values(permissions=sorted(perms + ["customers.contracts"])))


def downgrade() -> None:
    raise NotImplementedError("downgrade is not supported")
