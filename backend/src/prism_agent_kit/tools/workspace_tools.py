"""工作区文件工具的契约与本地实现。"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.text_files import decode_utf8_prefix
from prism_agent_kit.core.workspace_paths import resolve_in_workspace
from prism_agent_kit.tools.contracts import (
    ToolDefinition,
    ToolExecutionContext,
)

type SearchCallback = Callable[[str, int], Awaitable[list[object]]]


class FileListInput(BaseModel):
    """列目录入参。"""

    path: str = "."


class FileListEntry(BaseModel):
    """目录项。"""

    name: str
    type: Literal["file", "dir"]
    size: int | None = None
    modified_at: float | None = None


class FileListOutput(BaseModel):
    """列目录结果。"""

    entries: list[FileListEntry]


class FileReadInput(BaseModel):
    """读文件入参。"""

    path: str
    max_bytes: int = Field(default=65_536, ge=1, le=200_000)


class FileReadOutput(BaseModel):
    """读文件结果。"""

    content: str
    truncated: bool
    size: int


class FileSearchInput(BaseModel):
    """检索入参。"""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)
    path_prefix: str | None = None


class FileSearchHit(BaseModel):
    """检索命中。"""

    path: str
    snippet: str


class FileSearchOutput(BaseModel):
    """检索结果。"""

    hits: list[FileSearchHit]


class FileWriteInput(BaseModel):
    """写文件入参。"""

    path: str
    content: str
    mode: Literal["overwrite", "append", "create"] = "overwrite"


class FileWriteOutput(BaseModel):
    """写文件结果。"""

    path: str
    bytes: int
    created: bool


def _root(context: ToolExecutionContext) -> Path:
    if context.workspace_root is None:
        raise AgentKitError(
            ErrorCode.WORKSPACE_NOT_BOUND,
            "尚未绑定工作区，请先在界面选择工作区目录",
            http_status=409,
        )
    return context.workspace_root


def _list_entries(target: Path) -> FileListOutput:
    from prism_agent_kit.core.workspace_paths import EXCLUDED_DIR_NAMES

    try:
        with os.scandir(target) as entries:
            items: list[FileListEntry] = []
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in EXCLUDED_DIR_NAMES:
                        continue
                    items.append(FileListEntry(name=entry.name, type="dir"))
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    items.append(
                        FileListEntry(
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
    return FileListOutput(entries=items)


def _read_file(target: Path, max_bytes: int) -> FileReadOutput:
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
        content = decode_utf8_prefix(raw)
    except UnicodeDecodeError as error:
        raise AgentKitError(
            ErrorCode.WORKSPACE_FILE_ENCODING,
            "文件不是合法 UTF-8 文本",
            http_status=400,
            details={"path": str(target)},
        ) from error
    return FileReadOutput(
        content=content,
        truncated=stat.st_size > len(raw),
        size=stat.st_size,
    )


def _write_file(target: Path, content: str, mode: str) -> FileWriteOutput:
    existed = target.exists()
    if mode == "create" and existed:
        raise AgentKitError(
            ErrorCode.WORKSPACE_PATH_INVALID,
            "目标文件已存在，create 模式不会覆盖",
            http_status=409,
            details={"path": str(target)},
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append":
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content)
    else:
        with target.open("w", encoding="utf-8") as handle:
            handle.write(content)
    return FileWriteOutput(
        path=str(target),
        bytes=len(content.encode("utf-8")),
        created=not existed,
    )


def build_workspace_tools() -> list[ToolDefinition]:
    """构造四个工作区工具定义。"""

    async def file_list(raw: FileListInput, context: ToolExecutionContext) -> FileListOutput:
        root = _root(context)
        target = resolve_in_workspace(root, raw.path)
        return await asyncio.to_thread(_list_entries, target)

    async def file_read(raw: FileReadInput, context: ToolExecutionContext) -> FileReadOutput:
        root = _root(context)
        target = resolve_in_workspace(root, raw.path)
        return await asyncio.to_thread(_read_file, target, raw.max_bytes)

    async def file_search(raw: FileSearchInput, context: ToolExecutionContext) -> FileSearchOutput:
        _root(context)
        if context.search is None:
            raise AgentKitError(
                ErrorCode.WORKSPACE_NOT_BOUND,
                "工作区检索不可用",
                http_status=409,
            )
        try:
            matches = await context.search(raw.query, raw.limit)
        except AgentKitError:
            raise
        hits = [FileSearchHit(path=str(item.path), snippet=str(item.snippet)) for item in matches]
        if raw.path_prefix:
            hits = [hit for hit in hits if hit.path.startswith(raw.path_prefix)]
        return FileSearchOutput(hits=hits)

    async def file_write(raw: FileWriteInput, context: ToolExecutionContext) -> FileWriteOutput:
        root = _root(context)
        target = resolve_in_workspace(root, raw.path)
        if ".git" in target.relative_to(root).parts:
            raise AgentKitError(
                ErrorCode.WORKSPACE_PATH_INVALID,
                "不允许写入 .git 目录",
                http_status=403,
                details={"path": raw.path},
            )
        return await asyncio.to_thread(_write_file, target, raw.content, raw.mode)

    def definition(
        name: str,
        description: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        handler: Callable[..., Awaitable[BaseModel]],
        timeout: float,
        *,
        requires_approval: bool = False,
    ) -> ToolDefinition:
        return ToolDefinition(
            name=name,
            description=description,
            input_model=input_model,
            output_model=output_model,
            execution_mode=ExecutionMode.LOCAL,
            timeout_seconds=timeout,
            handler=handler,
            requires_approval=requires_approval,
        )

    return [
        definition(
            "file_list",
            "列出工作区内某个目录下的文件与子目录。需要用户先绑定工作区。",
            FileListInput,
            FileListOutput,
            file_list,
            15,
        ),
        definition(
            "file_read",
            "读取工作区内的 UTF-8 文本文件，超长内容会截断。需要用户先绑定工作区。",
            FileReadInput,
            FileReadOutput,
            file_read,
            15,
        ),
        definition(
            "file_search",
            "按关键词检索工作区已索引的文本文件，返回命中片段。需要用户先绑定工作区。",
            FileSearchInput,
            FileSearchOutput,
            file_search,
            20,
        ),
        definition(
            "file_write",
            "把文本写入工作区内文件（overwrite/append/create）。写入需要用户在界面审批后才会执行。",
            FileWriteInput,
            FileWriteOutput,
            file_write,
            30,
            requires_approval=True,
        ),
    ]
