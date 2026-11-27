"""v1.4 model profiles, run snapshots and compaction checkpoints

Revision ID: 20261127_0007
Revises: 20261126_0006
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261127_0007"
down_revision: str | None = "20261126_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("api_key_env", sa.String(length=128), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_model_profiles"),
    )
    op.create_index("ux_model_profiles_name", "model_profiles", ["name"], unique=True)
    op.create_index(
        "ux_model_profiles_one_active",
        "model_profiles",
        ["is_active"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )
    op.add_column("runs", sa.Column("model_profile_id", sa.String(length=36), nullable=True))
    op.add_column("runs", sa.Column("model_context_window", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("model_max_output_tokens", sa.Integer(), nullable=True))
    op.create_table(
        "compaction_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("first_kept_message_id", sa.Integer(), nullable=False),
        sa.Column("tokens_before", sa.Integer(), nullable=False),
        sa.Column("tokens_after", sa.Integer(), nullable=False),
        sa.Column("pruned_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_compaction_checkpoints"),
    )
    op.create_index(
        "ix_checkpoints_session_created",
        "compaction_checkpoints",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_checkpoints_session_created", table_name="compaction_checkpoints")
    op.drop_table("compaction_checkpoints")
    op.drop_column("runs", "model_max_output_tokens")
    op.drop_column("runs", "model_context_window")
    op.drop_column("runs", "model_profile_id")
    op.drop_index("ux_model_profiles_one_active", table_name="model_profiles")
    op.drop_index("ux_model_profiles_name", table_name="model_profiles")
    op.drop_table("model_profiles")
