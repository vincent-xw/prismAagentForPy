import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from prism_agent_kit.application.mcp.config_service import McpConfigService, McpServerInput
from prism_agent_kit.application.mcp.manager import McpServerManager
from prism_agent_kit.core.mcp import McpStatus
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.registry import ToolRegistry

SERVER_SCRIPT = Path(__file__).resolve().parents[2] / "support" / "mcp_http_server.py"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise AssertionError("HTTP MCP 服务未在超时内就绪")


@pytest.fixture
def http_mcp_url():
    port = free_port()
    env = {**os.environ, "PORT": str(port)}
    process = subprocess.Popen([sys.executable, str(SERVER_SCRIPT)], env=env)
    try:
        wait_port(port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        process.wait(timeout=10)


async def make_manager(uow_factory: UnitOfWorkFactory) -> tuple[McpServerManager, McpConfigService]:
    registry = ToolRegistry()
    service = McpConfigService(uow_factory)
    return (
        McpServerManager(
            uow_factory=uow_factory,
            config_service=service,
            tool_registry=registry,
            connect_timeout_seconds=10,
            tool_timeout_seconds=10,
        ),
        service,
    )


async def test_http_server_handshake_and_call(
    uow_factory: UnitOfWorkFactory, http_mcp_url: str
) -> None:
    manager, service = await make_manager(uow_factory)
    server = await service.create(McpServerInput(name="web", transport="http", url=http_mcp_url))
    await service.set_enabled(server.id, True)
    await manager.start_all()
    try:
        assert (await service.get(server.id)).status is McpStatus.CONNECTED
        result = await manager.call_tool("mcp__web__echo", {"text": "ok"})
        assert result["text"] == "ok"
    finally:
        await manager.stop()


async def test_bad_http_server_marks_error(uow_factory: UnitOfWorkFactory) -> None:
    manager, service = await make_manager(uow_factory)
    server = await service.create(
        McpServerInput(name="dead", transport="http", url=f"http://127.0.0.1:{free_port()}/mcp")
    )
    await service.set_enabled(server.id, True)

    await manager.start_all()

    assert (await service.get(server.id)).status is McpStatus.ERROR
    await manager.stop()
