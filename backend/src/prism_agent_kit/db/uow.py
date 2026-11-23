from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from prism_agent_kit.db.repositories.events import EventRepository
from prism_agent_kit.db.repositories.messages import MessageRepository
from prism_agent_kit.db.repositories.runs import RunRepository
from prism_agent_kit.db.repositories.sessions import SessionRepository
from prism_agent_kit.db.repositories.tool_calls import ToolCallRepository
from prism_agent_kit.db.repositories.workspace_documents import WorkspaceDocumentRepository
from prism_agent_kit.db.repositories.workspaces import WorkspaceRepository


class UnitOfWork:
    """共享单个 AsyncSession 的短事务工作单元。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.sessions: SessionRepository
        self.runs: RunRepository
        self.messages: MessageRepository
        self.tool_calls: ToolCallRepository
        self.events: EventRepository
        self.workspaces: WorkspaceRepository
        self.workspace_documents: WorkspaceDocumentRepository

    async def __aenter__(self) -> Self:
        session = self._session_factory()
        self._session = session
        self.sessions = SessionRepository(session)
        self.runs = RunRepository(session)
        self.messages = MessageRepository(session)
        self.tool_calls = ToolCallRepository(session)
        self.events = EventRepository(session)
        self.workspaces = WorkspaceRepository(session)
        self.workspace_documents = WorkspaceDocumentRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        await session.rollback()
        await session.close()
        self._session = None

    async def commit(self) -> None:
        """提交当前事务。"""
        await self._require_session().commit()

    async def rollback(self) -> None:
        """回滚当前事务。"""
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork 必须在 async with 内使用")
        return self._session


class UnitOfWorkFactory:
    """按请求或按任务创建独立工作单元。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> UnitOfWork:
        return UnitOfWork(self._session_factory)
