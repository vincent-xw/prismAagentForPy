import pytest

from prism_agent_kit.application.mcp.config_service import McpConfigService, McpServerInput
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.db.uow import UnitOfWorkFactory


def make_service(
    uow_factory: UnitOfWorkFactory, env: dict[str, str] | None = None
) -> McpConfigService:
    return McpConfigService(uow_factory, parent_env=env or {})


async def test_rejects_plaintext_secret(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    with pytest.raises(AgentKitError) as error:
        await service.create(
            McpServerInput(
                name="demo",
                transport="stdio",
                command="python",
                env={"API_KEY": "sk-1234567890abcdef"},
            )
        )
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID


async def test_requires_transport_fields(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    with pytest.raises(AgentKitError) as error:
        await service.create(McpServerInput(name="demo", transport="stdio"))
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID
    with pytest.raises(AgentKitError) as error:
        await service.create(McpServerInput(name="demo", transport="http"))
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID


async def test_rejects_empty_name(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    with pytest.raises(AgentKitError) as error:
        await service.create(McpServerInput(name="   ", transport="http", url="https://e/mcp"))
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID


async def test_resolves_env_placeholder(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory, {"MY_TOKEN": "abc"})
    server = await service.create(
        McpServerInput(
            name="web",
            transport="http",
            url="https://mcp.example/mcp",
            headers={"Authorization": "Bearer ${MY_TOKEN}"},
        )
    )
    connection = await service.build_connection(server)
    assert connection.transport == "http"
    assert connection.params["headers"]["Authorization"] == "Bearer abc"


async def test_missing_placeholder_rejected(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    server = await service.create(
        McpServerInput(
            name="web",
            transport="http",
            url="https://e/mcp",
            headers={"X": "${MISSING_VAR}"},
        )
    )
    with pytest.raises(AgentKitError) as error:
        await service.build_connection(server)
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID


async def test_stdio_inherits_allowlisted_env(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory, {"PATH": "/usr/bin", "HOME": "/home/me", "SECRET": "x"})
    server = await service.create(
        McpServerInput(name="local", transport="stdio", command="python", args=["s.py"])
    )
    connection = await service.build_connection(server)
    assert connection.params.command == "python"
    assert connection.params.env["PATH"] == "/usr/bin"
    assert connection.params.env["HOME"] == "/home/me"
    assert "SECRET" not in connection.params.env


async def test_enable_and_list(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    server = await service.create(McpServerInput(name="local", transport="stdio", command="python"))
    updated = await service.set_enabled(server.id, True)
    assert updated.enabled is True
    assert [item.id for item in await service.list_servers()] == [server.id]


async def test_resolved_secret_rejected(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory, {"MY_TOKEN": "sk-abcdefghijklmnopqrstuvwxyz"})
    server = await service.create(
        McpServerInput(
            name="web",
            transport="http",
            url="https://e/mcp",
            headers={"Authorization": "Bearer ${MY_TOKEN}"},
        )
    )
    with pytest.raises(AgentKitError) as error:
        await service.build_connection(server)
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID


async def test_name_allows_underscore(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    server = await service.create(
        McpServerInput(name="deep_wiki", transport="http", url="https://e/mcp")
    )
    assert server.name == "deep_wiki"


async def test_name_accepts_mixed_case_and_normalizes_slug(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    server = await service.create(
        McpServerInput(name="DeepWiki", transport="http", url="https://e/mcp")
    )
    assert server.name == "DeepWiki"
    from prism_agent_kit.application.mcp.naming import slugify_name

    assert slugify_name(server.name) == "deepwiki"


async def test_duplicate_slug_rejected(uow_factory: UnitOfWorkFactory) -> None:
    service = make_service(uow_factory)
    await service.create(McpServerInput(name="deep_wiki", transport="http", url="https://a/mcp"))
    with pytest.raises(AgentKitError) as error:
        await service.create(
            McpServerInput(name="DEEP_WIKI", transport="http", url="https://b/mcp")
        )
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID
