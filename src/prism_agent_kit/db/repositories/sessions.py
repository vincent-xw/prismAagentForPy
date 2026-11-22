from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Session
from prism_agent_kit.db.mappers import session_to_domain, session_to_row
from prism_agent_kit.db.models import SessionRow


class SessionRepository:
    """Session 的读写仓库。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, title: str | None = None) -> Session:
        """创建并暂存一个 Session。由调用方决定是否提交。"""
        domain = Session(title=title)
        self._session.add(session_to_row(domain))
        await self._session.flush()
        return domain

    async def get(self, session_id: str) -> Session:
        """按 ID 读取 Session。不存在时抛出 404 领域错误。"""
        row = await self._session.get(SessionRow, session_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.SESSION_NOT_FOUND,
                "Session 不存在",
                http_status=404,
                details={"session_id": session_id},
            )
        return session_to_domain(row)

    async def list(self) -> list[Session]:
        """按最近活动时间倒序返回全部 Session。"""
        result = await self._session.scalars(
            select(SessionRow).order_by(SessionRow.updated_at.desc(), SessionRow.id.desc())
        )
        return [session_to_domain(row) for row in result]
