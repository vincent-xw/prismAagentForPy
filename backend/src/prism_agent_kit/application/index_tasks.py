"""工作区索引后台任务的生命周期管理。"""

from __future__ import annotations

import asyncio
from typing import Literal

from sqlalchemy.exc import OperationalError

from prism_agent_kit.application.workspace_indexer import WorkspaceIndexer
from prism_agent_kit.core.enums import IndexStatus
from prism_agent_kit.db.uow import UnitOfWorkFactory


class WorkspaceIndexTaskManager:
    """单飞地调度每个工作区的索引任务，并在关停时统一回收。"""

    def __init__(
        self,
        *,
        indexer: WorkspaceIndexer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._indexer = indexer
        self._uow_factory = uow_factory
        self._tasks: dict[str, asyncio.Task[object]] = {}

    async def submit(
        self,
        workspace_id: str,
        *,
        mode: Literal["full", "file"] = "full",
        rel_path: str | None = None,
    ) -> None:
        """提交一次索引；同一工作区已有任务在跑时直接返回。"""
        running = self._tasks.get(workspace_id)
        if running is not None and not running.done():
            return
        task: asyncio.Task[object] = asyncio.create_task(
            self._run(workspace_id, mode, rel_path),
            name=f"workspace-index-{workspace_id}",
        )
        self._tasks[workspace_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(workspace_id, None))

    async def _run(
        self,
        workspace_id: str,
        mode: Literal["full", "file"],
        rel_path: str | None,
    ) -> None:
        try:
            if mode == "file" and rel_path is not None:
                await self._indexer.index_file(workspace_id, rel_path)
            else:
                await self._indexer.rebuild(workspace_id)
        except Exception:
            return

    async def drain(self) -> None:
        """等待当前全部索引任务结束（供测试与关停使用）。"""
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        """取消并回收全部索引任务。"""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def reset_interrupted(self) -> int:
        """把上次进程遗留的 indexing 状态复位为 failed。"""
        try:
            async with self._uow_factory() as uow:
                workspaces = await uow.workspaces.list_with_status(IndexStatus.INDEXING)
                for workspace in workspaces:
                    await uow.workspaces.update_index_state(
                        workspace.id,
                        status=IndexStatus.FAILED,
                        error="process_interrupted",
                    )
                await uow.commit()
        except OperationalError:
            # 数据库尚未迁移（例如容器首次启动前）时没有索引状态可复位。
            return 0
        return len(workspaces)
