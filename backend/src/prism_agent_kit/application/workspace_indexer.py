"""工作区全文索引器：遍历目录、过滤不可索引文件并写入 FTS。"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from prism_agent_kit.core.enums import IndexStatus
from prism_agent_kit.core.models import utc_now
from prism_agent_kit.core.workspace_paths import EXCLUDED_DIR_NAMES
from prism_agent_kit.db.repositories.workspace_documents import IndexedDocument
from prism_agent_kit.db.uow import UnitOfWorkFactory

EXCLUDED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".7z",
        ".mp4",
        ".mov",
        ".woff",
        ".woff2",
        ".sqlite",
        ".db",
    }
)


@dataclass(frozen=True)
class IndexReport:
    """一次索引的结果。"""

    status: IndexStatus
    file_count: int
    error: str | None = None


def is_indexable_name(name: str) -> bool:
    """按文件名与扩展名判断是否允许进入索引。"""
    if name == ".env" or name.startswith(".env."):
        return False
    return Path(name).suffix.lower() not in EXCLUDED_EXTENSIONS


class WorkspaceIndexer:
    """把工作区文本文件写入 workspace_documents。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        max_file_bytes: int = 1_048_576,
        max_files: int = 20_000,
        max_total_bytes: int = 200 * 1024 * 1024,
    ) -> None:
        self._uow_factory = uow_factory
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes

    async def rebuild(self, workspace_id: str) -> IndexReport:
        """完整重建一个工作区的索引。"""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            await uow.workspaces.update_index_state(
                workspace_id, status=IndexStatus.INDEXING
            )
            await uow.commit()
        try:
            documents, truncated = await asyncio.to_thread(
                self._collect, Path(workspace.root_path)
            )
        except Exception as error:  # noqa: BLE001 - 遍历失败要落状态而不是抛给调用方
            return await self._mark_failed(workspace_id, error)

        async with self._uow_factory() as uow:
            await uow.workspace_documents.replace_all(workspace_id, documents)
            await uow.workspaces.update_index_state(
                workspace_id,
                status=IndexStatus.READY,
                file_count=len(documents),
                error="truncated_at_limit" if truncated else None,
                indexed_at=utc_now(),
            )
            await uow.commit()
        return IndexReport(
            status=IndexStatus.READY,
            file_count=len(documents),
            error="truncated_at_limit" if truncated else None,
        )

    async def index_file(self, workspace_id: str, rel_path: str) -> IndexReport:
        """只重建单个文件的索引行。"""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
        try:
            document = await asyncio.to_thread(
                self._read_document, Path(workspace.root_path), rel_path
            )
        except Exception as error:  # noqa: BLE001
            return await self._mark_failed(workspace_id, error)

        async with self._uow_factory() as uow:
            if document is None:
                await uow.workspace_documents.delete_file(workspace_id, rel_path)
            else:
                await uow.workspace_documents.upsert(workspace_id, document)
            file_count = await uow.workspace_documents.count(workspace_id)
            await uow.workspaces.update_index_state(
                workspace_id,
                status=IndexStatus.READY,
                file_count=file_count,
                indexed_at=utc_now(),
            )
            await uow.commit()
        return IndexReport(status=IndexStatus.READY, file_count=file_count)

    async def _mark_failed(self, workspace_id: str, error: Exception) -> IndexReport:
        """把索引失败写回状态，错误文本只保留异常类型。"""
        async with self._uow_factory() as uow:
            await uow.workspaces.update_index_state(
                workspace_id,
                status=IndexStatus.FAILED,
                error=f"index_failed:{type(error).__name__}",
            )
            await uow.commit()
        return IndexReport(
            status=IndexStatus.FAILED,
            file_count=0,
            error=f"index_failed:{type(error).__name__}",
        )

    def _collect(self, root: Path) -> tuple[list[IndexedDocument], bool]:
        """同步遍历目录，收集可索引文本。"""
        documents: list[IndexedDocument] = []
        total_bytes = 0
        truncated = False
        for current, dir_names, file_names in os.walk(root):
            dir_names[:] = [name for name in dir_names if name not in EXCLUDED_DIR_NAMES]
            for name in sorted(file_names):
                if not is_indexable_name(name):
                    continue
                path = Path(current) / name
                try:
                    stat = path.lstat()
                except OSError:
                    continue
                if not path.is_file() or path.is_symlink():
                    continue
                if stat.st_size > self._max_file_bytes:
                    continue
                if len(documents) >= self._max_files or total_bytes >= self._max_total_bytes:
                    truncated = True
                    return documents, truncated
                try:
                    with path.open("rb") as handle:
                        raw = handle.read()
                except OSError:
                    continue
                if b"\x00" in raw[:4096]:
                    continue
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                documents.append(
                    IndexedDocument(
                        path=path.relative_to(root).as_posix(),
                        content=content,
                    )
                )
                total_bytes += len(raw)
        return documents, truncated

    def _read_document(self, root: Path, rel_path: str) -> IndexedDocument | None:
        """读取单个文件；不可索引时返回 None。"""
        from prism_agent_kit.core.workspace_paths import resolve_in_workspace

        path = resolve_in_workspace(root, rel_path)
        if not is_indexable_name(path.name):
            return None
        try:
            stat = path.lstat()
        except OSError:
            return None
        if not path.is_file() or path.is_symlink() or stat.st_size > self._max_file_bytes:
            return None
        with path.open("rb") as handle:
            raw = handle.read()
        if b"\x00" in raw[:4096]:
            return None
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return IndexedDocument(
            path=path.relative_to(root).as_posix(),
            content=content,
        )
