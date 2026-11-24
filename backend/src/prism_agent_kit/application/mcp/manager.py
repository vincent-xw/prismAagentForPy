"""MCP 服务的连接管理器：每个启用的服务一个独占会话的 worker。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

from pydantic import JsonValue

from prism_agent_kit.application.mcp.adapter import (
    McpToolInfo,
    normalize_result,
    to_tool_definition,
)
from prism_agent_kit.application.mcp.config_service import McpConfigService, McpConnection
from prism_agent_kit.core.enums import RunStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.mcp import McpServer, McpStatus
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolDefinition
from prism_agent_kit.tools.registry import ToolRegistry

_ACTIVE_RUN_STATUSES = (
    RunStatus.RUNNING,
    RunStatus.WAITING_FOR_TOOL,
    RunStatus.WAITING_FOR_APPROVAL,
)


class McpClientLike(Protocol):
    """SDK Client 中本模块用到的最小表面。"""

    async def list_tools(self) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


ClientFactory = Callable[[McpConnection], AbstractAsyncContextManager[McpClientLike]]


@asynccontextmanager
async def open_default_client(connection: McpConnection) -> AsyncIterator[McpClientLike]:
    """用官方 SDK 打开一个 MCP 客户端会话。"""
    from mcp import Client
    from mcp.client.streamable_http import (  # type: ignore[attr-defined]
        create_mcp_http_client,
        streamable_http_client,
    )

    if connection.transport == "stdio":
        async with Client(connection.params) as client:
            yield client
        return
    http_client = create_mcp_http_client(headers=connection.params.get("headers"))
    try:
        async with Client(
            streamable_http_client(connection.params["url"], http_client=http_client)
        ) as client:
            yield client
    finally:
        await http_client.aclose()


class McpWorker:
    """单服务的会话宿主：所有请求都在持有 Client 上下文的任务里执行。"""

    def __init__(
        self,
        *,
        server: McpServer,
        connection: McpConnection,
        client_factory: ClientFactory,
        on_tools: Callable[[McpServer, list[McpToolInfo]], list[ToolDefinition]],
        on_close: Callable[[], None],
        timeout_seconds: float,
        connect_timeout_seconds: float,
    ) -> None:
        self._server = server
        self._connection = connection
        self._factory = client_factory
        self._on_tools = on_tools
        self._on_close = on_close
        self._timeout = timeout_seconds
        self._connect_timeout = connect_timeout_seconds
        self._queue: asyncio.Queue[tuple[str, dict[str, Any], asyncio.Future[Any]] | None] = (
            asyncio.Queue()
        )
        self._ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._startup_error: BaseException | None = None
        self._original: dict[str, str] = {}
        self._started_tools = False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"mcp-{self._server.id}")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=self._connect_timeout)
        except TimeoutError as error:
            await self.stop()
            raise AgentKitError(
                ErrorCode.MCP_SERVER_UNAVAILABLE,
                "MCP 服务连接超时",
                http_status=503,
            ) from error
        if self._startup_error is not None:
            await self.stop()
            raise AgentKitError(
                ErrorCode.MCP_SERVER_UNAVAILABLE,
                f"MCP 服务连接失败: {type(self._startup_error).__name__}",
                http_status=503,
            ) from self._startup_error

    async def _run(self) -> None:
        try:
            async with self._factory(self._connection) as client:
                listed = await client.list_tools()
                infos = [
                    McpToolInfo(
                        name=str(tool.name),
                        description=str(getattr(tool, "description", "") or ""),
                        input_schema=dict(getattr(tool, "input_schema", {}) or {}),
                    )
                    for tool in listed.tools
                ]
                definitions = self._on_tools(self._server, infos)
                self._original = {
                    d.name: info.name for d, info in zip(definitions, infos, strict=True)
                }
                self._started_tools = True
                self._ready.set()
                while True:
                    request = await self._queue.get()
                    if request is None:
                        break
                    full_name, arguments, future = request
                    try:
                        result = await client.call_tool(
                            self._original.get(full_name, full_name), arguments
                        )
                        future.set_result(result)
                    except BaseException as error:
                        future.set_exception(error)
        except BaseException as error:
            self._startup_error = error
            self._ready.set()
        finally:
            if self._started_tools:
                self._on_close()

    async def call_tool(self, full_name: str, arguments: dict[str, Any]) -> Any:
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self._queue.put((full_name, arguments, future))
        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except TimeoutError as error:
            raise AgentKitError(
                ErrorCode.MCP_TOOL_TIMEOUT,
                "MCP 工具调用超时",
                http_status=504,
            ) from error

    async def stop(self) -> None:
        await self._queue.put(None)
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(BaseException):
                await self._task
            self._task = None


class McpServerManager:
    """MCP 服务的启停、重连与工具调用入口。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        config_service: McpConfigService,
        tool_registry: ToolRegistry,
        client_factory: ClientFactory | None = None,
        connect_timeout_seconds: float = 10.0,
        tool_timeout_seconds: float = 30.0,
        max_result_bytes: int = 204_800,
    ) -> None:
        self._uow_factory = uow_factory
        self._config = config_service
        self._registry = tool_registry
        self._factory = client_factory or open_default_client
        self._connect_timeout = connect_timeout_seconds
        self._tool_timeout = tool_timeout_seconds
        self._max_result_bytes = max_result_bytes
        self._workers: dict[str, McpWorker] = {}
        self._server_tools: dict[str, list[str]] = {}

    async def start_all(self) -> None:
        """连接所有已启用服务；单个失败只影响自身状态。"""
        servers = [item for item in await self._config.list_servers() if item.enabled]
        if not servers:
            return
        await asyncio.gather(
            *(self._connect_quietly(server.id) for server in servers),
            return_exceptions=True,
        )

    async def _connect_quietly(self, server_id: str) -> None:
        try:
            await self.connect(server_id)
        except AgentKitError:
            return

    async def connect(self, server_id: str) -> None:
        if server_id in self._workers:
            await self.disconnect(server_id)
        server = await self._config.get(server_id)
        connection = await self._config.build_connection(server)
        worker = McpWorker(
            server=server,
            connection=connection,
            client_factory=self._factory,
            on_tools=self._register_tools,
            on_close=self._make_on_close(server.name),
            timeout_seconds=self._tool_timeout,
            connect_timeout_seconds=self._connect_timeout,
        )
        try:
            await worker.start()
        except AgentKitError as error:
            await self._config.set_status(server_id, McpStatus.ERROR, error.message)
            raise
        self._workers[server_id] = worker
        await self._config.set_status(server_id, McpStatus.CONNECTED, None)

    async def disconnect(self, server_id: str) -> None:
        worker = self._workers.pop(server_id, None)
        if worker is not None:
            await worker.stop()
        await self._config.set_status(server_id, McpStatus.DISABLED, None)

    async def reconnect(self, server_id: str) -> None:
        await self._ensure_no_active_run()
        await self.disconnect(server_id)
        await self.connect(server_id)

    async def set_enabled(self, server_id: str, enabled: bool) -> None:
        await self._ensure_no_active_run()
        await self._config.set_enabled(server_id, enabled)
        if enabled:
            await self.connect(server_id)
        else:
            await self.disconnect(server_id)

    async def call_tool(self, full_name: str, arguments: dict[str, Any]) -> JsonValue:
        server_id = self._owner_of(full_name)
        worker = self._workers.get(server_id)
        if worker is None:
            raise AgentKitError(
                ErrorCode.MCP_DISABLED,
                "MCP 服务当前不可用",
                http_status=409,
                details={"tool_name": full_name},
            )
        result = await worker.call_tool(full_name, arguments)
        return normalize_result(result, self._max_result_bytes)

    async def stop(self) -> None:
        workers = list(self._workers.values())
        self._workers.clear()
        self._server_tools.clear()
        await asyncio.gather(*(worker.stop() for worker in workers), return_exceptions=True)

    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            definition
            for names in self._server_tools.values()
            for definition in (
                self._registry.get(name) for name in names if name in self._registry_names()
            )
        ]

    def _registry_names(self) -> set[str]:
        return {tool.name for tool in self._registry.list_tools()}

    def _owner_of(self, full_name: str) -> str:
        for server_id, names in self._server_tools.items():
            if full_name in names:
                return server_id
        raise AgentKitError(
            ErrorCode.MCP_DISABLED,
            "MCP 工具未注册",
            http_status=409,
            details={"tool_name": full_name},
        )

    def _make_on_close(self, server_name: str) -> Callable[[], None]:
        prefix = f"mcp__{server_name}__"

        def on_close() -> None:
            self._registry.unregister_by_prefix(prefix)

        return on_close

    def _register_tools(
        self,
        server: McpServer,
        infos: list[McpToolInfo],
    ) -> list[ToolDefinition]:
        definitions = [
            to_tool_definition(
                server,
                info,
                self._make_invoke(server.id),
                timeout_seconds=self._tool_timeout,
            )
            for info in infos
        ]
        for definition in definitions:
            self._registry.register(definition)
        self._server_tools[server.id] = [definition.name for definition in definitions]
        return definitions

    def _make_invoke(self, server_id: str) -> Callable[[str, dict[str, Any]], Awaitable[JsonValue]]:
        async def invoke(full_name: str, arguments: dict[str, Any]) -> JsonValue:
            return await self.call_tool(full_name, arguments)

        return invoke

    async def _ensure_no_active_run(self) -> None:
        async with self._uow_factory() as uow:
            for status in _ACTIVE_RUN_STATUSES:
                if await uow.runs.list_by_status(status):
                    raise AgentKitError(
                        ErrorCode.MCP_SERVER_BUSY,
                        "有活动 Run 时不能启用、禁用或重连 MCP 服务",
                        http_status=409,
                    )
