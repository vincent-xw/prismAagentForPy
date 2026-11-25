from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from prism_agent_kit.core.models import utc_now


class McpStatus(StrEnum):
    """MCP 服务连接状态。"""

    DISABLED = "disabled"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class McpServer(BaseModel):
    """用户配置的 MCP 服务。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    transport: Literal["stdio", "http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = False
    status: McpStatus = McpStatus.DISABLED
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
