import sys
from pathlib import Path

import pytest

from prism_agent_kit.application.mcp.config_service import McpConfigService, McpServerInput
from prism_agent_kit.application.mcp.manager import McpServerManager
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.registry import ToolRegistry

SERVER_SCRIPT = Path(__file__).resolve().parents[2] / "support" / "mcp_stdio_server.py"


async def start_manager(
    uow_factory: UnitOfWorkFactory,
    *,
    tool_timeout: float = 5.0,
) -> McpServerManager:
    registry = ToolRegistry()
    service = McpConfigService(uow_factory)
    server = await service.create(
        McpServerInput(
            name="demo",
            transport="stdio",
            command=sys.executable,
            args=[str(SERVER_SCRIPT)],
        )
    )
    await service.set_enabled(server.id, True)
    manager = McpServerManager(
        uow_factory=uow_factory,
        config_service=service,
        tool_registry=registry,
        connect_timeout_seconds=10,
        tool_timeout_seconds=tool_timeout,
    )
    await manager.start_all()
    return manager


async def test_stdio_tools_registered_and_called(uow_factory: UnitOfWorkFactory) -> None:
    manager = await start_manager(uow_factory)
    try:
        names = {tool.name for tool in manager.tool_definitions()}
        assert {"mcp__demo__echo", "mcp__demo__slow", "mcp__demo__boom"} <= names

        result = await manager.call_tool("mcp__demo__echo", {"text": "hi"})
        assert result["text"] == "hi"
    finally:
        await manager.stop()


async def test_stdio_tool_timeout(uow_factory: UnitOfWorkFactory) -> None:
    manager = await start_manager(uow_factory, tool_timeout=0.2)
    try:
        with pytest.raises(AgentKitError) as error:
            await manager.call_tool("mcp__demo__slow", {"seconds": 5})
        assert error.value.code is ErrorCode.MCP_TOOL_TIMEOUT
    finally:
        await manager.stop()


async def test_stdio_tool_error_maps(uow_factory: UnitOfWorkFactory) -> None:
    manager = await start_manager(uow_factory)
    try:
        with pytest.raises(AgentKitError) as error:
            await manager.call_tool("mcp__demo__boom", {})
        assert error.value.code is ErrorCode.MCP_TOOL_ERROR
    finally:
        await manager.stop()
