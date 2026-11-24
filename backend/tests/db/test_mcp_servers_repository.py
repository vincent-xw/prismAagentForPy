import pytest

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.mcp import McpServer, McpStatus
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_mcp_server_crud(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        server = await uow.mcp_servers.create(
            McpServer(name="demo", transport="stdio", command="python", args=["s.py"], env={})
        )
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.mcp_servers.get(server.id)
        assert loaded.name == "demo"
        assert loaded.status is McpStatus.DISABLED
        updated = await uow.mcp_servers.set_status(server.id, McpStatus.ERROR, "boom")
        await uow.commit()
        assert updated.last_error == "boom"

    async with uow_factory() as uow:
        enabled = await uow.mcp_servers.list_enabled()
        assert enabled == []
        await uow.mcp_servers.update(server.id, enabled=True)
        await uow.commit()
        assert [item.id for item in await uow.mcp_servers.list_enabled()] == [server.id]


async def test_mcp_server_get_missing(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.mcp_servers.get("missing")
        assert error.value.code is ErrorCode.MCP_SERVER_NOT_FOUND


async def test_mcp_server_delete(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        server = await uow.mcp_servers.create(
            McpServer(name="demo", transport="http", url="https://e/mcp")
        )
        await uow.commit()
        await uow.mcp_servers.delete(server.id)
        await uow.commit()
    async with uow_factory() as uow:
        assert await uow.mcp_servers.list_all() == []
