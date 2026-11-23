from prism_agent_kit.db.repositories.workspace_documents import (
    IndexedDocument,
    ensure_fts_supported,
)
from prism_agent_kit.db.uow import UnitOfWorkFactory


def test_fts_supported() -> None:
    assert ensure_fts_supported() is True


async def test_search_hits_chinese_and_two_char_fallback(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        await uow.workspace_documents.replace_all(
            "ws-1",
            [
                IndexedDocument(
                    path="docs/guide.md", content="这是一个关于工作区检索的中文测试文档"
                ),
                IndexedDocument(path="docs/other.md", content="unrelated english text"),
            ],
        )
        await uow.commit()

    async with uow_factory() as uow:
        long_hits = await uow.workspace_documents.search(
            "ws-1", "工作区检索", limit=10, path_prefix=None
        )
        assert [hit.path for hit in long_hits] == ["docs/guide.md"]
        assert "工作区" in long_hits[0].snippet

        short_hits = await uow.workspace_documents.search(
            "ws-1", "检索", limit=10, path_prefix=None
        )
        assert [hit.path for hit in short_hits] == ["docs/guide.md"]


async def test_prefix_filter_and_delete_workspace(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        await uow.workspace_documents.replace_all(
            "ws-1",
            [
                IndexedDocument(path="a/x.md", content="alpha keyword"),
                IndexedDocument(path="b/y.md", content="alpha keyword"),
            ],
        )
        await uow.commit()

    async with uow_factory() as uow:
        hits = await uow.workspace_documents.search("ws-1", "alpha", limit=10, path_prefix="b/")
        assert [hit.path for hit in hits] == ["b/y.md"]
        await uow.workspace_documents.delete_workspace("ws-1")
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.workspace_documents.count("ws-1") == 0


async def test_replace_all_replaces_previous_rows(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        await uow.workspace_documents.replace_all(
            "ws-1", [IndexedDocument(path="a.md", content="first version")]
        )
        await uow.workspace_documents.replace_all(
            "ws-1", [IndexedDocument(path="a.md", content="second version")]
        )
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.workspace_documents.count("ws-1") == 1
        hits = await uow.workspace_documents.search("ws-1", "second", limit=10, path_prefix=None)
        assert len(hits) == 1
