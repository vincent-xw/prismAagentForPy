"""把 MCP 工具适配为现有 ToolDefinition，并规范化调用结果。"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, JsonValue

from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.mcp import McpServer
from prism_agent_kit.tools.contracts import ToolDefinition, ToolExecutionContext

type McpInvoke = Callable[[str, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class McpToolInfo:
    """MCP 服务声明的工具信息。"""

    name: str
    description: str = ""
    input_schema: dict[str, JsonValue] = field(default_factory=dict)


class McpToolInput(BaseModel):
    """MCP 工具参数：保留服务端声明的任意字段。"""

    model_config = ConfigDict(extra="allow")


def to_tool_definition(
    server: McpServer,
    tool: McpToolInfo,
    invoke: McpInvoke,
    *,
    timeout_seconds: float,
) -> ToolDefinition:
    """构造 MCP 工具的 ToolDefinition；一律要求审批。"""
    from prism_agent_kit.application.mcp.naming import tool_name_for

    full_name = tool_name_for(server.name, tool.name)

    async def handler(raw: McpToolInput, _context: ToolExecutionContext) -> JsonValue:
        return cast(JsonValue, await invoke(full_name, raw.model_dump()))

    return ToolDefinition(
        name=full_name,
        description=tool.description or f"MCP 工具 {tool.name}",
        input_model=McpToolInput,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=timeout_seconds,
        requires_approval=True,
        input_schema_override=tool.input_schema,
        handler=handler,
    )


def normalize_result(result: Any, max_bytes: int) -> JsonValue:
    """把 CallToolResult 规范化为 JSON，并限制文本大小、丢弃二进制。"""
    texts: list[str] = []
    images: list[dict[str, JsonValue]] = []
    resources: list[dict[str, JsonValue]] = []
    for item in getattr(result, "content", []) or []:
        kind = getattr(item, "type", "")
        if kind == "text":
            texts.append(str(getattr(item, "text", "")))
        elif kind in {"image", "audio"}:
            data = str(getattr(item, "data", ""))
            images.append(
                {
                    "type": kind,
                    "mimeType": str(getattr(item, "mime_type", "")),
                    "size": max(0, (len(data) * 3) // 4),
                }
            )
        elif kind == "resource":
            resources.append({"type": "resource"})
    text = "\n".join(texts)
    if getattr(result, "is_error", False):
        raise AgentKitError(
            ErrorCode.MCP_TOOL_ERROR,
            (text or "MCP 工具返回错误")[:500],
            http_status=400,
        )
    truncated = len(text.encode("utf-8")) > max_bytes
    encoded = text.encode("utf-8")[:max_bytes]
    output: dict[str, JsonValue] = {
        "text": encoded.decode("utf-8", errors="ignore"),
        "truncated": truncated,
    }
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        raw = json.dumps(structured, ensure_ascii=False, default=str)
        if len(raw.encode("utf-8")) > max_bytes:
            output["structured"] = {"truncated": True}
        else:
            output["structured"] = structured
    if images:
        output["images"] = cast(JsonValue, images)
    if resources:
        output["resources"] = cast(JsonValue, resources)
    return output
