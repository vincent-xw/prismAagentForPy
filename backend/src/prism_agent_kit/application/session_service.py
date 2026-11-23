from __future__ import annotations

from collections.abc import Sequence

from prism_agent_kit.core.models import Message, Session
from prism_agent_kit.db.uow import UnitOfWorkFactory


class SessionService:
    """管理 Session 与消息查询的应用服务。"""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        workspace_service: object | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._workspace_service = workspace_service

    async def create(self, title: str | None = None) -> Session:
        """创建并提交一个 Session，并绑定创建时的活跃工作区。"""
        workspace_id = None
        if self._workspace_service is not None:
            active = await self._workspace_service.active()  # type: ignore[attr-defined]
            workspace_id = active.id if active is not None else None
        async with self._uow_factory() as uow:
            session = await uow.sessions.create(title=title, workspace_id=workspace_id)
            await uow.commit()
        return session

    async def set_workspace(self, session_id: str, workspace_id: str | None) -> Session:
        """把已有会话重新绑定到工作区；工作区必须存在。"""
        async with self._uow_factory() as uow:
            if workspace_id is not None:
                await uow.workspaces.get(workspace_id)
            session = await uow.sessions.set_workspace(session_id, workspace_id)
            await uow.commit()
        return session

    async def list(self) -> list[Session]:
        """按最近活动顺序列出 Session。"""
        async with self._uow_factory() as uow:
            return await uow.sessions.list()

    async def get(self, session_id: str) -> Session:
        """读取指定 Session。"""
        async with self._uow_factory() as uow:
            return await uow.sessions.get(session_id)

    async def list_messages(self, session_id: str) -> Sequence[Message]:
        """按全局顺序读取 Session 消息。"""
        async with self._uow_factory() as uow:
            await uow.sessions.get(session_id)
            return await uow.messages.list_for_session(session_id)
