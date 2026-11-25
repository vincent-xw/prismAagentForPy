"""MCP 服务管理接口。"""

from typing import Any, cast

from fastapi import APIRouter, status

from prism_agent_kit.api.dependencies import McpConfigServiceDependency, McpManagerDependency
from prism_agent_kit.api.schemas import McpServerCreate, McpServerView, McpToolsView, McpToolView
from prism_agent_kit.application.mcp.config_service import McpServerInput
from prism_agent_kit.core.mcp import McpServer

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _to_input(payload: McpServerCreate) -> McpServerInput:
    return McpServerInput(**payload.model_dump())


def _mask(values: dict[str, str]) -> dict[str, str]:
    """占位符原样返回，字面量值统一掩码。"""
    return {key: value if "${" in value else "***" for key, value in values.items()}


def _to_view(server: McpServer, tool_count: int) -> McpServerView:
    return McpServerView(
        id=server.id,
        name=server.name,
        transport=server.transport,
        command=server.command,
        args=list(server.args),
        url=server.url,
        enabled=server.enabled,
        status=server.status.value,
        last_error=server.last_error,
        tool_count=tool_count,
        env_keys=sorted(server.env),
        header_keys=sorted(server.headers),
        env=_mask(server.env),
        headers=_mask(server.headers),
    )


@router.get("/servers", response_model=list[McpServerView])
async def list_servers(
    config: McpConfigServiceDependency,
    manager: McpManagerDependency,
) -> list[McpServerView]:
    """返回全部 MCP 服务与工具数量。"""
    return [
        _to_view(server, len(manager.tool_definitions_for(server.id)))
        for server in await config.list_servers()
    ]


@router.post("/servers", response_model=McpServerView)
async def create_server(
    payload: McpServerCreate,
    config: McpConfigServiceDependency,
) -> McpServerView:
    """新增 MCP 服务。"""
    return _to_view(await config.create(_to_input(payload)), 0)


@router.patch("/servers/{server_id}", response_model=McpServerView)
async def update_server(
    server_id: str,
    payload: McpServerCreate,
    config: McpConfigServiceDependency,
    manager: McpManagerDependency,
) -> McpServerView:
    """更新 MCP 服务配置。"""
    server = await manager.update_server(server_id, _to_input(payload))
    return _to_view(server, len(manager.tool_definitions_for(server_id)))


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: str,
    manager: McpManagerDependency,
) -> None:
    """删除 MCP 服务：先断开连接并释放工具。"""
    await manager.remove_server(server_id)


@router.post("/servers/{server_id}/enable", response_model=McpServerView)
async def enable_server(
    server_id: str,
    config: McpConfigServiceDependency,
    manager: McpManagerDependency,
) -> McpServerView:
    """启用并连接 MCP 服务。"""
    await manager.set_enabled(server_id, True)
    return _to_view(await config.get(server_id), len(manager.tool_definitions_for(server_id)))


@router.post("/servers/{server_id}/disable", response_model=McpServerView)
async def disable_server(
    server_id: str,
    config: McpConfigServiceDependency,
    manager: McpManagerDependency,
) -> McpServerView:
    """禁用并断开 MCP 服务。"""
    await manager.set_enabled(server_id, False)
    return _to_view(await config.get(server_id), 0)


@router.post("/servers/{server_id}/reconnect", response_model=McpServerView)
async def reconnect_server(
    server_id: str,
    config: McpConfigServiceDependency,
    manager: McpManagerDependency,
) -> McpServerView:
    """重连 MCP 服务并刷新工具。"""
    await manager.reconnect(server_id)
    return _to_view(await config.get(server_id), len(manager.tool_definitions_for(server_id)))


@router.get("/servers/{server_id}/tools", response_model=McpToolsView)
async def list_server_tools(
    server_id: str,
    config: McpConfigServiceDependency,
    manager: McpManagerDependency,
) -> McpToolsView:
    """返回该服务当前已注册的工具目录。"""
    await config.get(server_id)
    definitions = manager.tool_definitions_for(server_id)
    return McpToolsView(
        server_id=server_id,
        tools=[
            McpToolView(
                name=definition.name,
                description=definition.description,
                input_schema=cast(dict[str, Any], definition.to_model_schema()["function"])[
                    "parameters"
                ],
            )
            for definition in definitions
        ],
    )
