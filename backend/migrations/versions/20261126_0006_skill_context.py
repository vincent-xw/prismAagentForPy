"""skill context kind and run skill name

Revision ID: 20261126_0006
Revises: 20261124_0005
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261126_0006"
down_revision: str | None = "20261124_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="text"),
    )
    op.add_column("runs", sa.Column("skill_name", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "skill_name")
    op.drop_column("messages", "kind")
