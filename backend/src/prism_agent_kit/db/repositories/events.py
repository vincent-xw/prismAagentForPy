from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.models import RunEvent
from prism_agent_kit.db.mappers import run_event_to_domain, run_event_to_row
from prism_agent_kit.db.models import RunEventRow


class EventRepository:
    """可重放 Run 事件的持久化仓库。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: RunEvent) -> RunEvent:
        """追加一个事件并回填游标 ID。"""
        row = run_event_to_row(event)
        self._session.add(row)
        await self._session.flush()
        return run_event_to_domain(row)

    async def list_after(
        self,
        run_id: str,
        after_id: int | None = None,
    ) -> list[RunEvent]:
        """返回游标之后的持久事件。"""
        statement = select(RunEventRow).where(RunEventRow.run_id == run_id)
        if after_id is not None:
            statement = statement.where(RunEventRow.id > after_id)
        result = await self._session.scalars(statement.order_by(RunEventRow.id))
        return [run_event_to_domain(row) for row in result]

    async def last_id(self, run_id: str) -> int | None:
        """返回 Run 当前最大事件游标。"""
        return await self._session.scalar(
            select(func.max(RunEventRow.id)).where(RunEventRow.run_id == run_id)
        )
