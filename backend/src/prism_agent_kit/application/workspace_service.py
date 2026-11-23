"""工作区绑定、目录浏览、文本读取与检索的应用服务。"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.core.workspace_paths import EXCLUDED_DIR_NAMES, resolve_in_workspace
from prism_agent_kit.db.repositories.workspace_documents import SearchHit
from prism_agent_kit.db.uow import UnitOfWorkFactory

if TYPE_CHECKING:  # 仅为类型标注，避免运行时循环依赖
    from prism_agent_kit.application.index_tasks import WorkspaceIndexTaskManager


@dataclass(frozen=True)
class TreeEntry:
    """目录树中的一个条目。"""

    name: str
    type: str
    size: int | None = None
    modified_at: float | None = None


@dataclass(frozen=True)
class FileContent:
    """工作区文本文件内容。"""

    path: str
    content: str
    truncated: bool
    size: int


class WorkspaceService:
    """工作区生命周期与只读操作。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        index_tasks: WorkspaceIndexTaskManager | None = None,
        max_file_bytes: int = 1_048_576,
        max_files: int = 20_000,
        data_dir: Path | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._index_tasks = index_tasks
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files
        self._data_dir = data_dir.resolve() if data_dir is not None else None

    async def list_workspaces(self) -> list[Workspace]:
        """返回全部工作区。"""
        async with self._uow_factory() as uow:
            return await uow.workspaces.list_all()

    async def active(self) -> Workspace | None:
        """返回当前活跃工作区。"""
        async with self._uow_factory() as uow:
            return await uow.workspaces.get_active()

    async def get(self, workspace_id: str) -> Workspace:
        """按 ID 读取工作区。"""
        async with self._uow_factory() as uow:
            return await uow.workspaces.get(workspace_id)

    async def create(self, path: str, label: str | None = None) -> Workspace:
        """绑定并激活一个本地目录。"""
        root = await asyncio.to_thread(self._resolve_root_path, path)
        self._reject_data_dir_overlap(root)

        async with self._uow_factory() as uow:
            existing = await uow.workspaces.get_by_root(str(root))
            if existing is not None:
                activated = await uow.workspaces.activate(existing.id)
                await uow.commit()
                await self._submit_index(activated.id)
                return activated
            workspace = await uow.workspaces.create(
                Workspace(root_path=str(root), label=label or root.name)
            )
            workspace = await uow.workspaces.activate(workspace.id)
            await uow.commit()
        await self._submit_index(workspace.id)
        return workspace

    def _resolve_root_path(self, path: str) -> Path:
        """同步校验并规范化工作区根路径, 避免在事件循环里做阻塞 IO。"""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            raise AgentKitError(
                ErrorCode.WORKSPACE_PATH_INVALID,
                "工作区必须是绝对路径",
                http_status=400,
                details={"path": path},
            )
        if not candidate.exists():
            raise AgentKitError(
                ErrorCode.WORKSPACE_PATH_INVALID,
                "工作区目录不存在",
                http_status=400,
                details={"path": path},
            )
        if not candidate.is_dir():
            raise AgentKitError(
                ErrorCode.WORKSPACE_PATH_INVALID,
                "工作区必须是目录",
                http_status=400,
                details={"path": path},
            )
        return candidate.resolve()

    async def activate(self, workspace_id: str) -> Workspace:
        """切换活跃工作区并触发一次完整重建。"""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.activate(workspace_id)
            await uow.commit()
        await self._submit_index(workspace.id)
        return workspace

    async def delete(self, workspace_id: str) -> None:
        """删除工作区绑定与索引。"""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            await uow.workspaces.delete(workspace.id)
            await uow.workspace_documents.delete_workspace(workspace.id)
            await uow.commit()

    async def reindex(self, workspace_id: str) -> Workspace:
        """手动触发完整重建。"""
        workspace = await self.get(workspace_id)
        await self._submit_index(workspace.id)
        return workspace

    async def root_for(self, workspace_id: str | None) -> Path | None:
        """把工作区 ID 解析为根路径；未绑定或已删除返回 None。"""
        if workspace_id is None:
            return None
        async with self._uow_factory() as uow:
            try:
                workspace = await uow.workspaces.get(workspace_id)
            except AgentKitError:
                return None
        return Path(workspace.root_path)

    async def tree(self, workspace_id: str, rel: str = ".") -> list[TreeEntry]:
        """列出工作区某目录的直接子项。"""
        root = await self._require_root(workspace_id)
        target = resolve_in_workspace(root, rel)
        return await asyncio.to_thread(self._list_dir, target)

    async def read_file(
        self,
        workspace_id: str,
        rel: str,
        max_bytes: int = 65_536,
    ) -> FileContent:
        """读取工作区内的文本文件，超长截断。"""
        root = await self._require_root(workspace_id)
        target = resolve_in_workspace(root, rel)
        return await asyncio.to_thread(self._read_text, target, max_bytes)

    async def search(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int = 20,
        path_prefix: str | None = None,
    ) -> list[SearchHit]:
        """在工作区索引中检索。"""
        async with self._uow_factory() as uow:
            await uow.workspaces.get(workspace_id)
            return await uow.workspace_documents.search(
                workspace_id, query, limit=limit, path_prefix=path_prefix
            )

    async def pick_directory(self) -> str:
        """调用系统原生目录选择对话框。"""
        system = platform.system()
        if system == "Darwin":
            command = [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "选择工作区目录")',
            ]
        elif system == "Linux":
            command = ["zenity", "--file-selection", "--directory", "--title=选择工作区目录"]
        elif system == "Windows":
            command = [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
                "{ [Console]::WriteLine($dialog.SelectedPath) }",
            ]
        else:
            raise AgentKitError(
                ErrorCode.WORKSPACE_PICKER_UNAVAILABLE,
                "当前操作系统不支持原生目录选择",
                http_status=409,
                details={"reason": "unsupported"},
            )
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except FileNotFoundError as error:
            raise AgentKitError(
                ErrorCode.WORKSPACE_PICKER_UNAVAILABLE,
                "目录选择命令不可用",
                http_status=409,
                details={"reason": "unsupported"},
            ) from error
        except subprocess.TimeoutExpired as error:
            raise AgentKitError(
                ErrorCode.WORKSPACE_PICKER_UNAVAILABLE,
                "目录选择超时",
                http_status=409,
                details={"reason": "timeout"},
            ) from error
        selected = completed.stdout.strip()
        if completed.returncode != 0 or not selected:
            raise AgentKitError(
                ErrorCode.WORKSPACE_PICKER_UNAVAILABLE,
                "未选择目录",
                http_status=409,
                details={"reason": "cancelled"},
            )
        return selected

    async def status(self, workspace_id: str) -> Workspace:
        """读取工作区索引状态。"""
        return await self.get(workspace_id)

    async def _submit_index(self, workspace_id: str) -> None:
        if self._index_tasks is not None:
            await self._index_tasks.submit(workspace_id, mode="full")

    async def _require_root(self, workspace_id: str) -> Path:
        workspace = await self.get(workspace_id)
        return Path(workspace.root_path)

    def _reject_data_dir_overlap(self, root: Path) -> None:
        if self._data_dir is None:
            return
        if root == self._data_dir:
            raise AgentKitError(
                ErrorCode.WORKSPACE_PATH_INVALID,
                "工作区不能是应用数据目录",
                http_status=400,
                details={"path": str(root)},
            )
        if root in self._data_dir.parents:
            raise AgentKitError(
                ErrorCode.WORKSPACE_PATH_INVALID,
                "工作区与应用数据目录不能重叠",
                http_status=400,
                details={"path": str(root)},
            )

    def _list_dir(self, target: Path) -> list[TreeEntry]:
        try:
            with os.scandir(target) as entries:
                items: list[TreeEntry] = []
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in EXCLUDED_DIR_NAMES:
                            continue
                        items.append(TreeEntry(name=entry.name, type="dir"))
                    elif entry.is_file(follow_symlinks=False):
                        stat = entry.stat(follow_symlinks=False)
                        items.append(
                            TreeEntry(
                                name=entry.name,
                                type="file",
                                size=stat.st_size,
                                modified_at=stat.st_mtime,
                            )
                        )
        except FileNotFoundError as error:
            raise AgentKitError(
                ErrorCode.WORKSPACE_FILE_NOT_FOUND,
                "目录不存在",
                http_status=404,
                details={"path": str(target)},
            ) from error
        items.sort(key=lambda item: (item.type != "dir", item.name.lower()))
        return items

    def _read_text(self, target: Path, max_bytes: int) -> FileContent:
        try:
            stat = target.lstat()
        except FileNotFoundError as error:
            raise AgentKitError(
                ErrorCode.WORKSPACE_FILE_NOT_FOUND,
                "文件不存在",
                http_status=404,
                details={"path": str(target)},
            ) from error
        if not target.is_file() or target.is_symlink():
            raise AgentKitError(
                ErrorCode.WORKSPACE_FILE_NOT_FOUND,
                "目标不是普通文件",
                http_status=404,
                details={"path": str(target)},
            )
        with target.open("rb") as handle:
            head = handle.read(4096)
            if b"\x00" in head:
                raise AgentKitError(
                    ErrorCode.WORKSPACE_FILE_BINARY,
                    "是二进制文件，无法作为文本读取",
                    http_status=400,
                    details={"path": str(target)},
                )
            handle.seek(0)
            raw = handle.read(max_bytes)
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AgentKitError(
                ErrorCode.WORKSPACE_FILE_ENCODING,
                "文件不是合法 UTF-8 文本",
                http_status=400,
                details={"path": str(target)},
            ) from error
        return FileContent(
            path=str(target),
            content=content,
            truncated=stat.st_size > len(raw),
            size=stat.st_size,
        )
