from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.mcp import McpServer, McpStatus
from prism_agent_kit.core.models import utc_now
from prism_agent_kit.db.mappers import mcp_server_to_domain, mcp_server_to_row
from prism_agent_kit.db.models import McpServerRow


class McpServerRepository:
    """MCP 服务配置的读写仓库。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, server: McpServer) -> McpServer:
        self._session.add(mcp_server_to_row(server))
        await self._session.flush()
        return server

    async def get(self, server_id: str) -> McpServer:
        row = await self._session.get(McpServerRow, server_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.MCP_SERVER_NOT_FOUND,
                "MCP 服务不存在",
                http_status=404,
                details={"server_id": server_id},
            )
        return mcp_server_to_domain(row)

    async def list_all(self) -> list[McpServer]:
        result = await self._session.scalars(
            select(McpServerRow).order_by(McpServerRow.created_at, McpServerRow.id)
        )
        return [mcp_server_to_domain(row) for row in result]

    async def list_enabled(self) -> list[McpServer]:
        result = await self._session.scalars(
            select(McpServerRow).where(McpServerRow.enabled == 1).order_by(McpServerRow.name)
        )
        return [mcp_server_to_domain(row) for row in result]

    async def update(
        self,
        server_id: str,
        *,
        name: str | None = None,
        transport: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> McpServer:
        row = await self._require_row(server_id)
        if name is not None:
            row.name = name
        if transport is not None:
            row.transport = transport
        if command is not None:
            row.command = command
        if args is not None:
            row.args_json = args
        if env is not None:
            row.env_json = env
        if url is not None:
            row.url = url
        if headers is not None:
            row.headers_json = headers
        if enabled is not None:
            row.enabled = 1 if enabled else 0
        row.updated_at = _now()
        await self._session.flush()
        await self._session.refresh(row)
        return mcp_server_to_domain(row)

    async def set_status(
        self,
        server_id: str,
        status: McpStatus,
        error: str | None = None,
    ) -> McpServer:
        row = await self._require_row(server_id)
        row.status = status.value
        row.last_error = error
        row.updated_at = _now()
        await self._session.flush()
        await self._session.refresh(row)
        return mcp_server_to_domain(row)

    async def delete(self, server_id: str) -> None:
        row = await self._session.get(McpServerRow, server_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.MCP_SERVER_NOT_FOUND,
                "MCP 服务不存在",
                http_status=404,
                details={"server_id": server_id},
            )
        await self._session.delete(row)
        await self._session.flush()

    async def _require_row(self, server_id: str) -> McpServerRow:
        row = await self._session.get(McpServerRow, server_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.MCP_SERVER_NOT_FOUND,
                "MCP 服务不存在",
                http_status=404,
                details={"server_id": server_id},
            )
        return row


def _now() -> datetime:
    return utc_now().replace(tzinfo=None)
