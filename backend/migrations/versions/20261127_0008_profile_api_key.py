"""model profile api_key column

Revision ID: 20261127_0008
Revises: 20261127_0007
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261127_0008"
down_revision: str | None = "20261127_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 密钥可存库；为空时回退 api_key_env 指向的环境变量。
    op.add_column("model_profiles", sa.Column("api_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("model_profiles", "api_key")
