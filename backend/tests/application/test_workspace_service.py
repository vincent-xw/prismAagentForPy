from pathlib import Path

import pytest

from prism_agent_kit.application.workspace_service import WorkspaceService
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.db.uow import UnitOfWorkFactory


class RecordingIndexTasks:
    """记录索引触发，避免测试里真的遍历目录。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def submit(
        self, workspace_id: str, *, mode: str = "full", rel_path: str | None = None
    ) -> None:
        self.calls.append((mode, workspace_id))


@pytest.fixture
def index_tasks() -> RecordingIndexTasks:
    return RecordingIndexTasks()


@pytest.fixture
def service(
    uow_factory: UnitOfWorkFactory, index_tasks: RecordingIndexTasks, tmp_path: Path
) -> WorkspaceService:
    return WorkspaceService(
        uow_factory=uow_factory,
        index_tasks=index_tasks,
        data_dir=tmp_path / "app-data",
    )


async def test_create_workspace_normalizes_and_activates(
    service: WorkspaceService, tmp_path: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()

    workspace = await service.create(str(root / "."))

    assert workspace.root_path == str(root.resolve())
    assert workspace.is_active is True
    assert workspace.label == "proj"


async def test_create_rejects_relative_or_file(service: WorkspaceService, tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")

    with pytest.raises(AgentKitError) as error:
        await service.create("relative/path")
    assert error.value.code is ErrorCode.WORKSPACE_PATH_INVALID

    with pytest.raises(AgentKitError) as error:
        await service.create(str(tmp_path / "f.txt"))
    assert error.value.code is ErrorCode.WORKSPACE_PATH_INVALID


async def test_create_rejects_app_data_overlap(service: WorkspaceService, tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    app_data.mkdir()

    with pytest.raises(AgentKitError) as error:
        await service.create(str(app_data))
    assert error.value.code is ErrorCode.WORKSPACE_PATH_INVALID


async def test_create_is_idempotent_for_same_root(
    service: WorkspaceService, index_tasks: RecordingIndexTasks, tmp_path: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()

    first = await service.create(str(root))
    second = await service.create(str(root))

    assert first.id == second.id
    assert [entry.id for entry in await service.list_workspaces()] == [first.id]


async def test_activate_switches_and_triggers_index(
    service: WorkspaceService, index_tasks: RecordingIndexTasks, tmp_path: Path
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = await service.create(str(tmp_path / "a"))
    second = await service.create(str(tmp_path / "b"))

    await service.activate(first.id)

    active = await service.active()
    assert active is not None and active.id == first.id
    assert ("full", first.id) in index_tasks.calls
    assert second.is_active is True


async def test_tree_excludes_git_and_reads_truncated(
    service: WorkspaceService, tmp_path: Path
) -> None:
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "a.txt").write_text("x" * 50, encoding="utf-8")
    workspace = await service.create(str(root))

    entries = await service.tree(workspace.id, ".")
    assert {entry.name for entry in entries} == {"docs"}
    assert entries[0].type == "dir"

    content = await service.read_file(workspace.id, "docs/a.txt", max_bytes=10)
    assert content.truncated is True
    assert len(content.content) == 10


async def test_read_rejects_binary(service: WorkspaceService, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "bin.dat").write_bytes(b"abc\x00def")
    workspace = await service.create(str(root))

    with pytest.raises(AgentKitError) as error:
        await service.read_file(workspace.id, "bin.dat")
    assert error.value.code is ErrorCode.WORKSPACE_FILE_BINARY


async def test_read_missing_file_raises(service: WorkspaceService, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    workspace = await service.create(str(root))

    with pytest.raises(AgentKitError) as error:
        await service.read_file(workspace.id, "nope.txt")
    assert error.value.code is ErrorCode.WORKSPACE_FILE_NOT_FOUND


async def test_search_delegates_to_index(
    service: WorkspaceService, uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    from prism_agent_kit.db.repositories.workspace_documents import IndexedDocument

    root = tmp_path / "proj"
    root.mkdir()
    workspace = await service.create(str(root))
    async with uow_factory() as uow:
        await uow.workspace_documents.replace_all(
            workspace.id, [IndexedDocument(path="docs/a.md", content="工作区检索测试")]
        )
        await uow.commit()

    hits = await service.search(workspace.id, "工作区检索")
    assert [hit.path for hit in hits] == ["docs/a.md"]


async def test_root_for_returns_none_when_unbound(service: WorkspaceService) -> None:
    assert await service.root_for(None) is None


async def test_read_multibyte_file_truncates_on_char_boundary(
    service: WorkspaceService, tmp_path: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "cn.txt").write_text("测试" * 40_000, encoding="utf-8")
    workspace = await service.create(str(root))

    content = await service.read_file(workspace.id, "cn.txt", max_bytes=65_536)

    assert content.truncated is True
    assert content.content.startswith("测试")
    assert len(content.content.encode("utf-8")) <= 65_536
