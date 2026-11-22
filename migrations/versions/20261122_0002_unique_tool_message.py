"""unique tool message per call

Revision ID: 20261122_0002
Revises: 20261122_0001
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0002"
down_revision: str | None = "20261122_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ux_messages_run_tool_call",
        "messages",
        ["run_id", "tool_call_id"],
        unique=True,
        sqlite_where=sa.text("tool_call_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_messages_run_tool_call", table_name="messages")
