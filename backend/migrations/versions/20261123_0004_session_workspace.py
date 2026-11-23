"""session workspace binding

Revision ID: 20261123_0004
Revises: 20261123_0003
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261123_0004"
down_revision: str | None = "20261123_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_sessions_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # 用每个会话最早一个带工作区的 Run 回填，保持历史会话的项目归属。
    op.execute(
        """
        UPDATE sessions
        SET workspace_id = (
            SELECT runs.workspace_id
            FROM runs
            WHERE runs.session_id = sessions.id
              AND runs.workspace_id IS NOT NULL
            ORDER BY runs.created_at, runs.id
            LIMIT 1
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("fk_sessions_workspace_id", type_="foreignkey")
        batch.drop_column("workspace_id")
