import asyncio
from pathlib import Path

import pytest

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.tools.contracts import ToolExecutionContext
from prism_agent_kit.tools.workspace_tools import (
    FileListInput,
    FileReadInput,
    FileWriteInput,
    build_workspace_tools,
)


def tools_by_name():
    return {tool.name: tool for tool in build_workspace_tools()}


def context(root: Path | None) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="run-1",
        session_id="session-1",
        call_id="call-1",
        cancel=asyncio.Event(),
        workspace_root=root,
    )


async def test_file_list_and_read(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("hello", encoding="utf-8")
    tools = tools_by_name()

    listed = await tools["file_list"].handler(FileListInput(path="."), context(root))
    assert [entry.name for entry in listed.entries] == ["docs"]

    read = await tools["file_read"].handler(
        FileReadInput(path="docs/a.md", max_bytes=3), context(root)
    )
    assert read.truncated is True
    assert read.content == "hel"


async def test_tools_without_workspace(tmp_path: Path) -> None:
    tools = tools_by_name()

    with pytest.raises(AgentKitError) as error:
        await tools["file_list"].handler(FileListInput(path="."), context(None))
    assert error.value.code is ErrorCode.WORKSPACE_NOT_BOUND


async def test_write_requires_approval_and_rejects_escape(tmp_path: Path) -> None:
    tools = tools_by_name()
    assert tools["file_write"].requires_approval is True
    root = tmp_path / "ws"
    root.mkdir()

    with pytest.raises(AgentKitError) as error:
        await tools["file_write"].handler(
            FileWriteInput(path="../x.txt", content="x"), context(root)
        )
    assert error.value.code is ErrorCode.WORKSPACE_PATH_OUTSIDE


async def test_write_modes(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    tools = tools_by_name()

    created = await tools["file_write"].handler(
        FileWriteInput(path="notes.md", content="hello", mode="create"), context(root)
    )
    assert created.created is True
    assert (root / "notes.md").read_text(encoding="utf-8") == "hello"

    appended = await tools["file_write"].handler(
        FileWriteInput(path="notes.md", content=" world", mode="append"), context(root)
    )
    assert appended.bytes == 6
    assert (root / "notes.md").read_text(encoding="utf-8") == "hello world"

    with pytest.raises(AgentKitError):
        await tools["file_write"].handler(
            FileWriteInput(path="notes.md", content="x", mode="create"), context(root)
        )


async def test_write_rejects_git_directory(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / ".git").mkdir(parents=True)
    tools = tools_by_name()

    with pytest.raises(AgentKitError) as error:
        await tools["file_write"].handler(
            FileWriteInput(path=".git/config", content="x"), context(root)
        )
    assert error.value.code is ErrorCode.WORKSPACE_PATH_INVALID


async def test_file_search_uses_injected_callback(tmp_path: Path) -> None:
    from dataclasses import dataclass

    from prism_agent_kit.tools.workspace_tools import FileSearchInput

    @dataclass(frozen=True)
    class Hit:
        path: str
        snippet: str

    async def search(query: str, limit: int) -> list[Hit]:
        return [Hit(path="docs/a.md", snippet="[工作区检索]")]

    root = tmp_path / "ws"
    root.mkdir()
    context_with_search = ToolExecutionContext(
        run_id="run-1",
        session_id="session-1",
        call_id="call-1",
        cancel=asyncio.Event(),
        workspace_root=root,
        workspace_id="ws-1",
        search=search,
    )

    output = await tools_by_name()["file_search"].handler(
        FileSearchInput(query="工作区检索"), context_with_search
    )
    assert [hit.path for hit in output.hits] == ["docs/a.md"]
    assert output.hits[0].snippet == "[工作区检索]"


async def test_file_search_without_workspace_rejected() -> None:
    from prism_agent_kit.tools.workspace_tools import FileSearchInput

    with pytest.raises(AgentKitError) as error:
        await tools_by_name()["file_search"].handler(
            FileSearchInput(query="anything"), context(None)
        )
    assert error.value.code is ErrorCode.WORKSPACE_NOT_BOUND


def test_workspace_write_approval_can_be_disabled() -> None:
    from prism_agent_kit.tools.workspace_tools import build_workspace_tools

    tools = {tool.name: tool for tool in build_workspace_tools(require_approval=False)}
    assert tools["file_write"].requires_approval is False
    assert {tool.name for tool in build_workspace_tools()} == set(tools)
    assert {tool.name: tool for tool in build_workspace_tools()}[
        "file_write"
    ].requires_approval is True
