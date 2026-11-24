import asyncio
import subprocess
import sys
import time
from pathlib import Path

from prism_agent_kit.application.mcp.config_service import McpConfigService, McpServerInput
from prism_agent_kit.application.mcp.manager import McpServerManager
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.registry import ToolRegistry

SERVER_SCRIPT = Path(__file__).resolve().parents[2] / "support" / "mcp_stdio_server.py"


def child_pids(script: Path) -> list[int]:
    output = subprocess.run(
        ["ps", "-eo", "pid=,command="], capture_output=True, text=True, check=True
    ).stdout
    pids: list[int] = []
    for line in output.splitlines():
        if str(script) in line:
            pids.append(int(line.strip().split()[0]))
    return pids


async def test_stop_leaves_no_child_process(uow_factory: UnitOfWorkFactory) -> None:
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
        tool_timeout_seconds=5,
    )
    await manager.start_all()
    assert child_pids(SERVER_SCRIPT), "stdio 子进程应已启动"

    await manager.stop()

    deadline = time.time() + 5
    while time.time() < deadline and child_pids(SERVER_SCRIPT):  # noqa: ASYNC110
        await asyncio.sleep(0.1)
    assert child_pids(SERVER_SCRIPT) == []
