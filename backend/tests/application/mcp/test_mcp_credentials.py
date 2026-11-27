"""MCP 凭据入库：明文保存、*** 掩码与还原。"""

from prism_agent_kit.application.mcp.config_service import McpConfigService, McpServerInput
from prism_agent_kit.db.uow import UnitOfWorkFactory


def make_service(uow_factory: UnitOfWorkFactory) -> McpConfigService:
    return McpConfigService(uow_factory, parent_env={})


async def test_plain_headers_are_stored(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)

    server = await service.create(
        McpServerInput(
            name="remote",
            transport="http",
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer sk-demo"},
        )
    )

    assert server.headers == {"Authorization": "Bearer sk-demo"}


async def test_masked_value_is_restored_on_update(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    created = await service.create(
        McpServerInput(
            name="remote",
            transport="http",
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer sk-demo"},
        )
    )

    updated = await service.update(
        created.id,
        McpServerInput(
            name="remote",
            transport="http",
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "***"},
        ),
    )

    assert updated.headers == {"Authorization": "Bearer sk-demo"}


async def test_placeholder_still_resolves(uow_factory: UnitOfWorkFactory) -> None:
    service = McpConfigService(uow_factory, parent_env={"MCP_TOKEN": "abc"})
    server = await service.create(
        McpServerInput(
            name="placeholder",
            transport="http",
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer ${MCP_TOKEN}"},
        )
    )

    connection = await service.build_connection(server)
    assert connection.params["headers"]["Authorization"] == "Bearer abc"
