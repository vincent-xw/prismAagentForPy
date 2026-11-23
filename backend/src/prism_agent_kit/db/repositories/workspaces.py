from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.enums import IndexStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import utc_now
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.db.mappers import workspace_to_domain, workspace_to_row
from prism_agent_kit.db.models import WorkspaceRow


class WorkspaceRepository:
    """工作区绑定的读写仓库。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, workspace: Workspace) -> Workspace:
        """创建并暂存工作区。由调用方提交事务。"""
        self._session.add(workspace_to_row(workspace))
        await self._session.flush()
        return workspace

    async def get(self, workspace_id: str) -> Workspace:
        """按 ID 读取；不存在抛 404。"""
        row = await self._session.get(WorkspaceRow, workspace_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.WORKSPACE_NOT_FOUND,
                "工作区不存在",
                http_status=404,
                details={"workspace_id": workspace_id},
            )
        return workspace_to_domain(row)

    async def get_by_root(self, root_path: str) -> Workspace | None:
        """按规范化根路径查找。"""
        row = await self._session.scalar(
            select(WorkspaceRow).where(WorkspaceRow.root_path == root_path)
        )
        return None if row is None else workspace_to_domain(row)

    async def get_active(self) -> Workspace | None:
        """返回当前唯一活跃工作区。"""
        row = await self._session.scalar(select(WorkspaceRow).where(WorkspaceRow.is_active == 1))
        return None if row is None else workspace_to_domain(row)

    async def list_all(self) -> list[Workspace]:
        """按创建时间返回全部工作区。"""
        result = await self._session.scalars(
            select(WorkspaceRow).order_by(WorkspaceRow.created_at, WorkspaceRow.id)
        )
        return [workspace_to_domain(row) for row in result]

    async def activate(self, workspace_id: str) -> Workspace:
        """把目标置为唯一活跃工作区。"""
        row = await self._session.get(WorkspaceRow, workspace_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.WORKSPACE_NOT_FOUND,
                "工作区不存在",
                http_status=404,
                details={"workspace_id": workspace_id},
            )
        now = utc_now().replace(tzinfo=None)
        await self._session.execute(
            update(WorkspaceRow)
            .where(WorkspaceRow.is_active == 1, WorkspaceRow.id != workspace_id)
            .values(is_active=0, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        row.is_active = 1
        row.updated_at = now
        await self._session.flush()
        await self._session.refresh(row)
        return workspace_to_domain(row)

    async def update_index_state(
        self,
        workspace_id: str,
        *,
        status: IndexStatus,
        file_count: int | None = None,
        error: str | None = None,
        indexed_at: datetime | None = None,
    ) -> Workspace:
        """更新索引状态；file_count 为空时不覆盖。"""
        row = await self._session.get(WorkspaceRow, workspace_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.WORKSPACE_NOT_FOUND,
                "工作区不存在",
                http_status=404,
                details={"workspace_id": workspace_id},
            )
        row.index_status = status.value
        row.index_error = error
        if file_count is not None:
            row.file_count = file_count
        if indexed_at is not None:
            row.indexed_at = indexed_at.replace(tzinfo=None)
        row.updated_at = utc_now().replace(tzinfo=None)
        await self._session.flush()
        await self._session.refresh(row)
        return workspace_to_domain(row)

    async def list_with_status(self, status: IndexStatus) -> list[Workspace]:
        """按索引状态列出工作区。"""
        result = await self._session.scalars(
            select(WorkspaceRow).where(WorkspaceRow.index_status == status.value)
        )
        return [workspace_to_domain(row) for row in result]

    async def delete(self, workspace_id: str) -> None:
        """删除非活跃工作区绑定。"""
        row = await self._session.get(WorkspaceRow, workspace_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.WORKSPACE_NOT_FOUND,
                "工作区不存在",
                http_status=404,
                details={"workspace_id": workspace_id},
            )
        if row.is_active == 1:
            raise AgentKitError(
                ErrorCode.RUN_CONFLICT,
                "活跃工作区不能删除，请先切换到其他工作区",
                http_status=409,
                details={"workspace_id": workspace_id, "reason": "workspace_active"},
            )
        await self._session.delete(row)
        await self._session.flush()
