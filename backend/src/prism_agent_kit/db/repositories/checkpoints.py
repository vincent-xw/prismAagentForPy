"""上下文 checkpoint 的持久化仓库。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.models import CompactionCheckpoint
from prism_agent_kit.db.mappers import checkpoint_to_domain, checkpoint_to_row
from prism_agent_kit.db.models import CompactionCheckpointRow


class CheckpointRepository:
    """按会话读写 checkpoint；原文消息不删除。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, checkpoint: CompactionCheckpoint) -> CompactionCheckpoint:
        self._session.add(checkpoint_to_row(checkpoint))
        await self._session.flush()
        return checkpoint

    async def latest(self, session_id: str) -> CompactionCheckpoint | None:
        row = await self._session.scalar(
            select(CompactionCheckpointRow)
            .where(CompactionCheckpointRow.session_id == session_id)
            .order_by(CompactionCheckpointRow.created_at.desc(), CompactionCheckpointRow.id.desc())
            .limit(1)
        )
        return None if row is None else checkpoint_to_domain(row)

    async def list_for_session(self, session_id: str) -> list[CompactionCheckpoint]:
        result = await self._session.scalars(
            select(CompactionCheckpointRow)
            .where(CompactionCheckpointRow.session_id == session_id)
            .order_by(CompactionCheckpointRow.created_at)
        )
        return [checkpoint_to_domain(row) for row in result]
