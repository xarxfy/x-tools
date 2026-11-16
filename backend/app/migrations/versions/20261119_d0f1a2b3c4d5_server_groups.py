"""server groups and tags

Revision ID: d0f1a2b3c4d5
Revises: c9e0f1a2b3c4
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = "d0f1a2b3c4d5"
down_revision = "c9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_groups",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("group_id", sa.String(12), nullable=True))
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))
        batch.create_foreign_key("fk_agents_group", "server_groups", ["group_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.drop_constraint("fk_agents_group", type_="foreignkey")
        batch.drop_column("tags")
        batch.drop_column("group_id")
    op.drop_table("server_groups")
