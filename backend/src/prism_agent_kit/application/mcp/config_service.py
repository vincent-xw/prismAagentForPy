"""MCP 服务配置的校验、持久化与连接参数构建。"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.mcp import McpServer
from prism_agent_kit.db.uow import UnitOfWorkFactory

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SECRET_PATTERNS = (
    re.compile(r"^sk-[A-Za-z0-9_-]{8,}$"),
    re.compile(r"^Bearer\s+\S{8,}$"),
    re.compile(r"^[A-Za-z0-9+/=_-]{32,}$"),
)
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT", "PATHEXT")


class McpServerInput(BaseModel):
    """新增/更新 MCP 服务的入参。"""

    name: str
    transport: Literal["stdio", "http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = False


@dataclass(frozen=True)
class McpConnection:
    """连接一个 MCP 服务所需的参数。"""

    transport: Literal["stdio", "http"]
    params: Any


class McpConfigService:
    """MCP 配置的校验与读写。"""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        parent_env: Mapping[str, str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._parent_env = dict(parent_env if parent_env is not None else os.environ)

    async def list_servers(self) -> list[McpServer]:
        async with self._uow_factory() as uow:
            return await uow.mcp_servers.list_all()

    async def get(self, server_id: str) -> McpServer:
        async with self._uow_factory() as uow:
            return await uow.mcp_servers.get(server_id)

    async def create(self, payload: McpServerInput) -> McpServer:
        fields = self._validate(payload)
        async with self._uow_factory() as uow:
            server = await uow.mcp_servers.create(McpServer(**fields))
            await uow.commit()
        return server

    async def update(self, server_id: str, payload: McpServerInput) -> McpServer:
        fields = self._validate(payload)
        async with self._uow_factory() as uow:
            await uow.mcp_servers.get(server_id)
            updated = await uow.mcp_servers.update(
                server_id,
                name=fields["name"],
                transport=fields["transport"],
                command=fields["command"],
                args=fields["args"],
                env=fields["env"],
                url=fields["url"],
                headers=fields["headers"],
                enabled=fields["enabled"],
            )
            await uow.commit()
        return updated

    async def delete(self, server_id: str) -> None:
        async with self._uow_factory() as uow:
            await uow.mcp_servers.delete(server_id)
            await uow.commit()

    async def set_enabled(self, server_id: str, enabled: bool) -> McpServer:
        async with self._uow_factory() as uow:
            updated = await uow.mcp_servers.update(server_id, enabled=enabled)
            await uow.commit()
        return updated

    async def set_status(self, server_id: str, status: Any, error: str | None = None) -> McpServer:
        async with self._uow_factory() as uow:
            updated = await uow.mcp_servers.set_status(server_id, status, error)
            await uow.commit()
        return updated

    async def build_connection(self, server: McpServer) -> McpConnection:
        """把配置解析为可用的连接参数。"""
        if server.transport == "stdio":
            env = self._build_env(server.env)
            self._reject_secrets({k: v for k, v in env.items() if k in server.env})
            if server.command is None:
                raise _invalid("stdio 服务缺少 command")
            return McpConnection(
                transport="stdio",
                params=StdioServerParameters(
                    command=server.command,
                    args=list(server.args),
                    env=env,
                ),
            )
        headers = self.resolve_placeholders(server.headers)
        self._reject_secrets(headers)
        if server.url is None:
            raise _invalid("http 服务缺少 url")
        return McpConnection(
            transport="http",
            params={"url": server.url, "headers": headers},
        )

    def resolve_placeholders(self, mapping: Mapping[str, str]) -> dict[str, str]:
        """替换值中的 ${VAR} 占位；缺失变量视为配置错误。"""
        resolved: dict[str, str] = {}
        for key, value in mapping.items():
            if not isinstance(value, str):
                raise _invalid(f"{key} 的值必须是字符串")

            def replace(match: re.Match[str]) -> str:
                name = match.group(1)
                if name not in self._parent_env:
                    raise _invalid(f"环境变量 {name} 未设置")
                return self._parent_env[name]

            resolved[key] = _PLACEHOLDER.sub(replace, value)
        return resolved

    def _validate(self, payload: McpServerInput) -> dict[str, Any]:
        if _SLUG.fullmatch(payload.name) is None:
            raise _invalid("服务名只能是小写字母、数字与连字符")
        if payload.transport == "stdio" and not payload.command:
            raise _invalid("stdio 服务必须提供 command")
        if payload.transport == "http" and not payload.url:
            raise _invalid("http 服务必须提供 url")
        self._reject_secrets(payload.env)
        self._reject_secrets(payload.headers)
        return {
            "name": payload.name,
            "transport": payload.transport,
            "command": payload.command,
            "args": list(payload.args),
            "env": dict(payload.env),
            "url": payload.url,
            "headers": dict(payload.headers),
            "enabled": payload.enabled,
        }

    @staticmethod
    def _reject_secrets(mapping: Mapping[str, str]) -> None:
        for key, value in mapping.items():
            if "${" in value:
                # 含占位符的值在连接时解析后再校验，避免误判 "Bearer ${TOKEN}"。
                continue
            if any(pattern.fullmatch(value) for pattern in _SECRET_PATTERNS):
                raise _invalid(f"{key} 疑似明文密钥，请改用 ${{VAR}} 引用环境变量")

    def _build_env(self, configured: Mapping[str, str]) -> dict[str, str]:
        env = {key: self._parent_env[key] for key in _ENV_ALLOWLIST if key in self._parent_env}
        env.update(self.resolve_placeholders(configured))
        return env


def _invalid(message: str) -> AgentKitError:
    return AgentKitError(
        ErrorCode.MCP_CONFIG_INVALID,
        message,
        http_status=400,
    )
