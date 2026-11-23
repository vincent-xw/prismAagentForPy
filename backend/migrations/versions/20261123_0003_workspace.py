"""workspace and fts5 documents

Revision ID: 20261123_0003
Revises: 20261122_0002
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261123_0003"
down_revision: str | None = "20261122_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_RUN_WHERE = (
    "status IN ('queued', 'running', 'waiting_for_tool', 'waiting_for_approval')"
)
_OLD_ACTIVE_RUN_WHERE = "status IN ('queued', 'running', 'waiting_for_tool')"


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("index_status", sa.String(length=16), nullable=False, server_default="idle"),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.UniqueConstraint("root_path", name="ux_workspaces_root_path"),
    )
    op.create_index(
        "ux_workspaces_single_active",
        "workspaces",
        ["is_active"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )

    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_runs_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.drop_index("ux_runs_one_active_per_session", table_name="runs")
    op.create_index(
        "ux_runs_one_active_per_session",
        "runs",
        ["session_id"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_RUN_WHERE),
    )

    op.execute(
        "CREATE VIRTUAL TABLE workspace_documents USING fts5("
        "workspace_id UNINDEXED, rel_path UNINDEXED, content, tokenize = 'trigram')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE workspace_documents")
    op.drop_index("ux_runs_one_active_per_session", table_name="runs")
    op.create_index(
        "ux_runs_one_active_per_session",
        "runs",
        ["session_id"],
        unique=True,
        sqlite_where=sa.text(_OLD_ACTIVE_RUN_WHERE),
    )
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("fk_runs_workspace_id", type_="foreignkey")
        batch.drop_column("workspace_id")
    op.drop_index("ux_workspaces_single_active", table_name="workspaces")
    op.drop_table("workspaces")
