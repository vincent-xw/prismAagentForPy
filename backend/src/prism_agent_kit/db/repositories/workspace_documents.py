"""工作区全文索引的 FTS5 读写仓库。"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_BATCH_SIZE = 200


@dataclass(frozen=True)
class IndexedDocument:
    """一条待入索引的文本文件。"""

    path: str
    content: str


@dataclass(frozen=True)
class SearchHit:
    """一次检索命中。"""

    path: str
    snippet: str


def ensure_fts_supported() -> bool:
    """检查当前 Python sqlite3 是否支持 FTS5 trigram 分词。"""
    try:
        connection = sqlite3.connect(":memory:")
    except sqlite3.Error:
        return False
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content, tokenize = 'trigram')")
        connection.execute("DROP TABLE probe")
    except sqlite3.Error:
        return False
    finally:
        connection.close()
    return True


def _build_snippet(content: str, query: str, *, radius: int = 40) -> str:
    """为短查询回退路径构造命中片段。"""
    index = content.find(query)
    if index < 0:
        return content[: radius * 2]
    start = max(0, index - radius)
    end = min(len(content), index + len(query) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


class WorkspaceDocumentRepository:
    """workspace_documents 虚拟表的读写。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_all(
        self,
        workspace_id: str,
        documents: Sequence[IndexedDocument],
    ) -> int:
        """清空该工作区旧索引后批量写入新文档。"""
        await self.delete_workspace(workspace_id)
        total = 0
        for start in range(0, len(documents), _BATCH_SIZE):
            batch = documents[start : start + _BATCH_SIZE]
            await self._session.execute(
                text(
                    "INSERT INTO workspace_documents (workspace_id, rel_path, content) "
                    "VALUES (:workspace_id, :rel_path, :content)"
                ),
                [
                    {
                        "workspace_id": workspace_id,
                        "rel_path": document.path,
                        "content": document.content,
                    }
                    for document in batch
                ],
            )
            total += len(batch)
        return total

    async def upsert(self, workspace_id: str, document: IndexedDocument) -> None:
        """替换单个文件的索引行。"""
        await self.delete_file(workspace_id, document.path)
        await self._session.execute(
            text(
                "INSERT INTO workspace_documents (workspace_id, rel_path, content) "
                "VALUES (:workspace_id, :rel_path, :content)"
            ),
            {
                "workspace_id": workspace_id,
                "rel_path": document.path,
                "content": document.content,
            },
        )

    async def delete_file(self, workspace_id: str, path: str) -> None:
        """删除单个文件的索引行。"""
        await self._session.execute(
            text(
                "DELETE FROM workspace_documents "
                "WHERE workspace_id = :workspace_id AND rel_path = :rel_path"
            ),
            {"workspace_id": workspace_id, "rel_path": path},
        )

    async def delete_workspace(self, workspace_id: str) -> None:
        """删除某工作区的全部索引行。"""
        await self._session.execute(
            text("DELETE FROM workspace_documents WHERE workspace_id = :workspace_id"),
            {"workspace_id": workspace_id},
        )

    async def count(self, workspace_id: str) -> int:
        """返回某工作区已索引的文件数。"""
        result = await self._session.execute(
            text("SELECT COUNT(*) FROM workspace_documents WHERE workspace_id = :workspace_id"),
            {"workspace_id": workspace_id},
        )
        return int(result.scalar_one())

    async def search(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int,
        path_prefix: str | None,
    ) -> list[SearchHit]:
        """检索工作区内容。3 字及以上走 FTS，短查询回退到受限 LIKE。"""
        keyword = query.strip()
        if not keyword:
            return []
        prefix_clause = ""
        params: dict[str, object] = {"workspace_id": workspace_id, "limit": limit}
        if path_prefix:
            prefix_clause = " AND rel_path LIKE :path_prefix"
            params["path_prefix"] = f"{path_prefix}%"

        if len(keyword) >= 3:
            params["query"] = keyword
            result = await self._session.execute(
                text(
                    "SELECT rel_path, "
                    "snippet(workspace_documents, 2, '[', ']', '…', 16) AS piece "
                    "FROM workspace_documents "
                    "WHERE workspace_documents MATCH :query "
                    "AND workspace_id = :workspace_id"
                    f"{prefix_clause} "
                    "ORDER BY bm25(workspace_documents) LIMIT :limit"
                ),
                params,
            )
            return [SearchHit(path=row.rel_path, snippet=row.piece) for row in result]

        params["query"] = keyword
        result = await self._session.execute(
            text(
                "SELECT rel_path, content FROM workspace_documents "
                "WHERE workspace_id = :workspace_id AND instr(content, :query) > 0"
                f"{prefix_clause} LIMIT :limit"
            ),
            params,
        )
        return [
            SearchHit(path=row.rel_path, snippet=_build_snippet(row.content, keyword))
            for row in result
        ]
