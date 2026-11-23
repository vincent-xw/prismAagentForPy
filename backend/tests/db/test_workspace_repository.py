from pathlib import Path

import pytest

from prism_agent_kit.core.enums import IndexStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_create_and_get_workspace(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    async with uow_factory() as uow:
        created = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "a")))
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.workspaces.get(created.id)
        assert loaded.root_path == str(tmp_path / "a")
        assert loaded.index_status is IndexStatus.IDLE
        assert loaded.is_active is False


async def test_get_missing_workspace_raises(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.workspaces.get("missing")
        assert error.value.code is ErrorCode.WORKSPACE_NOT_FOUND


async def test_activate_keeps_single_active(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    async with uow_factory() as uow:
        first = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "a")))
        second = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "b")))
        await uow.workspaces.activate(first.id)
        await uow.commit()

    async with uow_factory() as uow:
        await uow.workspaces.activate(second.id)
        await uow.commit()

    async with uow_factory() as uow:
        active = await uow.workspaces.get_active()
        assert active is not None and active.id == second.id
        refreshed_first = await uow.workspaces.get(first.id)
        assert refreshed_first.is_active is False


async def test_delete_active_workspace_rejected(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "a")))
        await uow.workspaces.activate(workspace.id)
        await uow.commit()

    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.workspaces.delete(workspace.id)
        assert error.value.code is ErrorCode.RUN_CONFLICT
        assert error.value.details["reason"] == "workspace_active"


async def test_update_index_state(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "a")))
        updated = await uow.workspaces.update_index_state(
            workspace.id,
            status=IndexStatus.READY,
            file_count=3,
        )
        await uow.commit()

    assert updated.index_status is IndexStatus.READY
    assert updated.file_count == 3
