from pathlib import Path

from prism_agent_kit.application.index_tasks import WorkspaceIndexTaskManager
from prism_agent_kit.application.workspace_indexer import WorkspaceIndexer
from prism_agent_kit.core.enums import IndexStatus
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.db.uow import UnitOfWorkFactory

_EXCLUDED_EXT = [".png", ".pdf", ".zip"]


def make_indexer(uow_factory: UnitOfWorkFactory) -> WorkspaceIndexer:
    return WorkspaceIndexer(
        uow_factory=uow_factory,
        max_file_bytes=1_048_576,
        max_files=20_000,
        max_total_bytes=8 * 1024 * 1024,
    )


async def test_rebuild_indexes_only_indexable_files(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("工作区检索测试", encoding="utf-8")
    (root / ".git" / "x.md").write_text("should skip", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    (root / "big.txt").write_text("x" * (2 * 1024 * 1024), encoding="utf-8")
    (root / "bin.dat").write_bytes(b"a\x00b")
    (root / "image.png").write_bytes(b"png")
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(root)))
        await uow.commit()

    report = await make_indexer(uow_factory).rebuild(workspace.id)

    assert report.status is IndexStatus.READY
    assert report.file_count == 1
    async with uow_factory() as uow:
        hits = await uow.workspace_documents.search(
            workspace.id, "工作区检索", limit=10, path_prefix=None
        )
        assert [hit.path for hit in hits] == ["docs/a.md"]
        refreshed = await uow.workspaces.get(workspace.id)
        assert refreshed.index_status is IndexStatus.READY
        assert refreshed.file_count == 1
        assert refreshed.indexed_at is not None


async def test_index_file_updates_single_document(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    root = tmp_path / "proj"
    (root).mkdir(parents=True)
    (root / "a.md").write_text("first", encoding="utf-8")
    (root / "b.md").write_text("second", encoding="utf-8")
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(root)))
        await uow.commit()
    indexer = make_indexer(uow_factory)
    await indexer.rebuild(workspace.id)

    (root / "a.md").write_text("updated content keyword", encoding="utf-8")
    report = await indexer.index_file(workspace.id, "a.md")

    assert report.status is IndexStatus.READY
    async with uow_factory() as uow:
        hits = await uow.workspace_documents.search(
            workspace.id, "keyword", limit=10, path_prefix=None
        )
        assert [hit.path for hit in hits] == ["a.md"]
        assert await uow.workspace_documents.count(workspace.id) == 2


async def test_reset_interrupted_marks_failed(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "p")))
        await uow.workspaces.update_index_state(workspace.id, status=IndexStatus.INDEXING)
        await uow.commit()

    manager = WorkspaceIndexTaskManager(
        indexer=make_indexer(uow_factory),
        uow_factory=uow_factory,
    )
    assert await manager.reset_interrupted() == 1
    async with uow_factory() as uow:
        refreshed = await uow.workspaces.get(workspace.id)
        assert refreshed.index_status is IndexStatus.FAILED
        assert refreshed.index_error == "process_interrupted"
