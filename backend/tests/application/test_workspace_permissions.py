"""工作区命名目录与权限档位。"""

import os
from pathlib import Path

import pytest

from prism_agent_kit.application.workspace_service import WorkspaceService
from prism_agent_kit.core.errors import AgentKitError
from prism_agent_kit.db.uow import UnitOfWorkFactory


@pytest.fixture()
def service(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> WorkspaceService:
    return WorkspaceService(
        uow_factory=uow_factory,
        workspace_root=tmp_path / "wsroot",
        workspace_user="tester",
        data_dir=tmp_path / "app-data",
    )


async def test_named_workspace_gets_suffix_on_conflict(service: WorkspaceService) -> None:
    first = await service.create(name="demo", permission_mode="workspace_write")
    second = await service.create(name="demo", permission_mode="workspace_write")

    assert first.root_path != second.root_path
    assert second.root_path.endswith("demo-2")
    assert second.name == "demo" and second.user == "tester"
    assert os.path.isdir(second.root_path)  # noqa: ASYNC240 - 测试内同步检查


async def test_default_permission_mode_is_workspace_write(service: WorkspaceService) -> None:
    workspace = await service.create(name="perm")
    assert workspace.permission_mode == "workspace_write"


async def test_invalid_permission_mode_is_422(service: WorkspaceService) -> None:
    with pytest.raises(AgentKitError) as error:
        await service.create(name="bad", permission_mode="root")
    assert error.value.http_status == 422


async def test_update_permission_round_trip(service: WorkspaceService) -> None:
    workspace = await service.create(name="toggle")

    updated = await service.update_permission(workspace.id, "read_only")

    assert updated.permission_mode == "read_only"
