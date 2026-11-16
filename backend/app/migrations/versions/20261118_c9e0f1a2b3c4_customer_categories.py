"""priority categories for customers

Revision ID: c9e0f1a2b3c4
Revises: b8d9e0f1a2b3
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "c9e0f1a2b3c4"
down_revision = "b8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_categories",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("category_id", sa.String(12), nullable=True))
        batch.create_foreign_key("fk_customers_category", "customer_categories", ["category_id"], ["id"],
                                 ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("customers") as batch:
        batch.drop_constraint("fk_customers_category", type_="foreignkey")
        batch.drop_column("category_id")
    op.drop_table("customer_categories")
