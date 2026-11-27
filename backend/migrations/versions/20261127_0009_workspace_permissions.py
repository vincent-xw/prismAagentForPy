"""workspace permissions and named workspace

Revision ID: 20261127_0009
Revises: 20261127_0008
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261127_0009"
down_revision: str | None = "20261127_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "permission_mode", sa.String(16), nullable=False, server_default="workspace_write"
        ),
    )
    op.add_column("workspaces", sa.Column("name", sa.String(128), nullable=True))
    op.add_column("workspaces", sa.Column("user", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "user")
    op.drop_column("workspaces", "name")
    op.drop_column("workspaces", "permission_mode")
