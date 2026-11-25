from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from mcp.types import TextContent

from prism_agent_kit.application.mcp.config_service import McpConfigService, McpServerInput
from prism_agent_kit.application.mcp.manager import McpServerManager
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.mcp import McpStatus
from prism_agent_kit.core.models import Run
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def list_tools(self) -> SimpleNamespace:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="echo",
                    description="echo",
                    input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                )
            ]
        )

    async def call_tool(self, name: str, arguments: dict[str, str]) -> SimpleNamespace:
        self.calls.append((name, arguments))
        return SimpleNamespace(
            content=[TextContent(type="text", text=str(arguments.get("text", "")))],
            structured_content=None,
            is_error=False,
        )


class FakeFactory:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.closed: list[str] = []
        self.clients: dict[str, FakeClient] = {}

    def __call__(self, connection):
        key = (
            connection.params.command
            if connection.transport == "stdio"
            else connection.params["url"]
        )

        @asynccontextmanager
        async def factory():
            if key in self.fail:
                raise RuntimeError("boom")
            client = FakeClient()
            self.clients[key] = client
            try:
                yield client
            finally:
                self.closed.append(key)

        return factory()


def make_manager(
    uow_factory: UnitOfWorkFactory, factory: FakeFactory, registry: ToolRegistry
) -> McpServerManager:
    return McpServerManager(
        uow_factory=uow_factory,
        config_service=McpConfigService(uow_factory, parent_env={"PATH": "/usr/bin"}),
        tool_registry=registry,
        client_factory=factory,
        connect_timeout_seconds=2,
        tool_timeout_seconds=2,
    )


async def add_server(uow_factory: UnitOfWorkFactory, name: str, *, enabled: bool = True):
    service = McpConfigService(uow_factory, parent_env={"PATH": "/usr/bin"})
    server = await service.create(McpServerInput(name=name, transport="stdio", command=name))
    if enabled:
        await service.set_enabled(server.id, True)
    return server


async def test_failed_server_does_not_block_others(uow_factory: UnitOfWorkFactory) -> None:
    registry = ToolRegistry()
    factory = FakeFactory(fail={"bad"})
    manager = make_manager(uow_factory, factory, registry)
    good = await add_server(uow_factory, "good")
    bad = await add_server(uow_factory, "bad")

    await manager.start_all()

    service = McpConfigService(uow_factory)
    assert (await service.get(good.id)).status is McpStatus.CONNECTED
    assert (await service.get(bad.id)).status is McpStatus.ERROR
    assert "mcp__good__echo" in {tool.name for tool in registry.list_tools()}
    assert all(not tool.name.startswith("mcp__bad__") for tool in registry.list_tools())
    await manager.stop()


async def test_call_tool_normalizes_result(uow_factory: UnitOfWorkFactory) -> None:
    registry = ToolRegistry()
    manager = make_manager(uow_factory, FakeFactory(), registry)
    await add_server(uow_factory, "good")
    await manager.start_all()

    result = await manager.call_tool("mcp__good__echo", {"text": "hi"})

    assert result["text"] == "hi"
    await manager.stop()


async def test_disable_blocked_while_run_active(uow_factory: UnitOfWorkFactory) -> None:
    registry = ToolRegistry()
    manager = make_manager(uow_factory, FakeFactory(), registry)
    good = await add_server(uow_factory, "good")
    await manager.start_all()
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        await uow.runs.create(
            Run(
                session_id=session.id,
                input_text="x",
                prompt_name="default",
                prompt_version="1",
                system_prompt="s",
                model="m",
            )
        )
        await uow.commit()
    async with uow_factory() as uow:
        await uow.runs.claim_next()
        await uow.commit()

    with pytest.raises(AgentKitError) as error:
        await manager.set_enabled(good.id, False)
    assert error.value.code is ErrorCode.MCP_SERVER_BUSY
    await manager.stop()


async def test_stop_reclaims_workers(uow_factory: UnitOfWorkFactory) -> None:
    registry = ToolRegistry()
    factory = FakeFactory()
    manager = make_manager(uow_factory, factory, registry)
    await add_server(uow_factory, "good")
    await manager.start_all()

    await manager.stop()

    assert factory.closed == ["good"]
    assert all(not tool.name.startswith("mcp__") for tool in registry.list_tools())


async def test_remove_server_disconnects_and_clears_tools(
    uow_factory: UnitOfWorkFactory,
) -> None:
    registry = ToolRegistry()
    factory = FakeFactory()
    manager = make_manager(uow_factory, factory, registry)
    server = await add_server(uow_factory, "good")
    await manager.start_all()

    await manager.remove_server(server.id)

    assert factory.closed == ["good"]
    assert all(not tool.name.startswith("mcp__") for tool in registry.list_tools())
    service = McpConfigService(uow_factory)
    with pytest.raises(AgentKitError) as error:
        await service.get(server.id)
    assert error.value.code is ErrorCode.MCP_SERVER_NOT_FOUND


async def test_remove_blocked_while_run_active(uow_factory: UnitOfWorkFactory) -> None:
    registry = ToolRegistry()
    manager = make_manager(uow_factory, FakeFactory(), registry)
    server = await add_server(uow_factory, "good")
    await manager.start_all()
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        await uow.runs.create(
            Run(
                session_id=session.id,
                input_text="x",
                prompt_name="default",
                prompt_version="1",
                system_prompt="s",
                model="m",
            )
        )
        await uow.commit()
    async with uow_factory() as uow:
        await uow.runs.claim_next()
        await uow.commit()

    with pytest.raises(AgentKitError) as error:
        await manager.remove_server(server.id)
    assert error.value.code is ErrorCode.MCP_SERVER_BUSY
    await manager.stop()


async def test_duplicate_sanitized_tool_names_rollback(uow_factory: UnitOfWorkFactory) -> None:
    class DuplicateFactory(FakeFactory):
        def __call__(self, connection):
            @asynccontextmanager
            async def factory():
                async def gen():
                    yield SimpleNamespace(
                        client=SimpleNamespace(
                            list_tools=self._list,
                            call_tool=self._call,
                        )
                    )

                client = SimpleNamespace(
                    list_tools=self._list,
                    call_tool=self._call,
                )
                yield client

            return factory()

        async def _list(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(name="a b", description="", input_schema={}),
                    SimpleNamespace(name="a_b", description="", input_schema={}),
                ]
            )

        async def _call(self, name, arguments):
            return SimpleNamespace(content=[], structured_content=None, is_error=False)

    registry = ToolRegistry()
    manager = make_manager(uow_factory, DuplicateFactory(), registry)
    server = await add_server(uow_factory, "dup")

    await manager.start_all()

    service = McpConfigService(uow_factory)
    assert (await service.get(server.id)).status is McpStatus.ERROR
    assert all(not tool.name.startswith("mcp__") for tool in registry.list_tools())


async def test_update_server_restores_masked_env(uow_factory: UnitOfWorkFactory) -> None:
    registry = ToolRegistry()
    manager = make_manager(uow_factory, FakeFactory(), registry)
    service = McpConfigService(uow_factory, parent_env={"PATH": "/usr/bin"})
    server = await service.create(
        McpServerInput(name="demo", transport="stdio", command="python", env={"PLAIN": "value"})
    )

    await manager.update_server(
        server.id,
        McpServerInput(name="demo", transport="stdio", command="python", env={"PLAIN": "***"}),
    )

    stored = await service.get(server.id)
    assert stored.env == {"PLAIN": "value"}


async def test_status_is_connecting_while_handshake(uow_factory: UnitOfWorkFactory) -> None:
    import asyncio as _asyncio

    release = _asyncio.Event()

    class SlowFactory(FakeFactory):
        def __call__(self, connection):
            @asynccontextmanager
            async def factory():
                await release.wait()
                client = FakeClient()
                try:
                    yield client
                finally:
                    self.closed.append("slow")

            return factory()

    registry = ToolRegistry()
    manager = make_manager(uow_factory, SlowFactory(), registry)
    server = await add_server(uow_factory, "slow")
    service = McpConfigService(uow_factory)

    task = _asyncio.create_task(manager.connect(server.id))
    deadline = _asyncio.get_running_loop().time() + 2
    while _asyncio.get_running_loop().time() < deadline:
        if (await service.get(server.id)).status is McpStatus.CONNECTING:
            break
        await _asyncio.sleep(0.01)
    assert (await service.get(server.id)).status is McpStatus.CONNECTING

    release.set()
    await task
    assert (await service.get(server.id)).status is McpStatus.CONNECTED
    await manager.stop()
