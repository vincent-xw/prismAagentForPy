"""文件工具的权限档位与删除语义。"""

import asyncio
from pathlib import Path

import pytest

from prism_agent_kit.core.errors import AgentKitError
from prism_agent_kit.tools.contracts import ToolExecutionContext
from prism_agent_kit.tools.workspace_tools import build_workspace_tools


def context(root: Path, mode: str) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="r",
        session_id="s",
        call_id="c",
        cancel=asyncio.Event(),
        workspace_root=root,
        permission_mode=mode,
    )


async def invoke(name: str, payload: dict, ctx: ToolExecutionContext):
    definition = next(
        item for item in build_workspace_tools(require_approval=False) if item.name == name
    )
    return await definition.handler(definition.input_model.model_validate(payload), ctx)


async def test_read_only_blocks_write_and_delete(tmp_path: Path) -> None:
    ctx = context(tmp_path, "read_only")
    with pytest.raises(AgentKitError) as write_error:
        await invoke("file_write", {"path": "a.txt", "content": "x", "mode": "create"}, ctx)
    assert write_error.value.code is not None
    assert "READ_ONLY" in str(write_error.value.code)

    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    with pytest.raises(AgentKitError) as delete_error:
        await invoke("file_delete", {"path": "b.txt"}, ctx)
    assert "READ_ONLY" in str(delete_error.value.code)


async def test_workspace_write_blocks_escape(tmp_path: Path) -> None:
    ctx = context(tmp_path, "workspace_write")
    with pytest.raises(AgentKitError) as error:
        await invoke("file_read", {"path": "../../etc/passwd"}, ctx)
    assert "PATH_OUTSIDE" in str(error.value.code)


async def test_write_read_and_delete_empty_dir(tmp_path: Path) -> None:
    ctx = context(tmp_path, "workspace_write")
    written = await invoke(
        "file_write", {"path": "dir/a.txt", "content": "hello", "mode": "create"}, ctx
    )
    assert written.created is True
    read = await invoke("file_read", {"path": "dir/a.txt"}, ctx)
    assert read.content == "hello"

    non_empty = tmp_path / "dir"
    with pytest.raises(AgentKitError) as error:
        await invoke("file_delete", {"path": "dir"}, ctx)
    assert "DIR_NOT_EMPTY" in str(error.value.code)

    await invoke("file_delete", {"path": "dir/a.txt"}, ctx)
    deleted = await invoke("file_delete", {"path": "dir"}, ctx)
    assert deleted.deleted is True and deleted.type == "dir"
    assert not non_empty.exists()


async def test_full_access_allows_outside_path(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"outside-{tmp_path.name}.txt"
    outside.write_text("out", encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ctx = context(workspace, "full_access")

    read = await invoke("file_read", {"path": str(outside)}, ctx)

    assert read.content == "out"
