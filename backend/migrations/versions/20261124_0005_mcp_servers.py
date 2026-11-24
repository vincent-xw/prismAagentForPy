"""mcp servers

Revision ID: 20261124_0005
Revises: 20261123_0004
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261124_0005"
down_revision: str | None = "20261123_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column("args_json", sa.JSON(), nullable=True),
        sa.Column("env_json", sa.JSON(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("headers_json", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="disabled"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_servers"),
    )
    op.create_index("ux_mcp_servers_name", "mcp_servers", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_mcp_servers_name", table_name="mcp_servers")
    op.drop_table("mcp_servers")
