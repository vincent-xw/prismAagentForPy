import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.core.errors import AgentKitError, ErrorCode

_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

type ProgressCallback = Callable[[JsonValue], Awaitable[None]]


class ToolExecutionContext(BaseModel):
    """工具执行所需的 Run 身份与协作式取消信号。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    session_id: str
    call_id: str
    cancel: asyncio.Event
    workspace_root: Path | None = None
    permission_mode: str | None = None
    workspace_id: str | None = None
    search: Callable[[str, int], Awaitable[list[Any]]] | None = None
    progress: ProgressCallback | None = None


type LocalToolHandler = Callable[
    [Any, ToolExecutionContext],
    Awaitable[Any] | Any,
]


class ToolExecutionResult(BaseModel):
    """工具执行结果。失败时携带稳定错误码而不抛出普通运行异常。"""

    ok: bool
    output: JsonValue = None
    error_code: ErrorCode | None = None
    error_message: str | None = None

    @classmethod
    def success(cls, output: JsonValue) -> "ToolExecutionResult":
        return cls(ok=True, output=output)

    @classmethod
    def failure(cls, code: ErrorCode, message: str) -> "ToolExecutionResult":
        return cls(ok=False, error_code=code, error_message=message)


class ToolDefinition(BaseModel):
    """注册给模型的工具契约。本地工具额外携带执行函数。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_model: type[Any]
    output_model: type[Any] | None
    execution_mode: ExecutionMode
    timeout_seconds: float = Field(gt=0)
    requires_approval: bool = False
    input_schema_override: dict[str, JsonValue] | None = None
    handler: LocalToolHandler | None = None

    def to_model_schema(self) -> dict[str, JsonValue]:
        """生成 OpenAI-compatible 模型工具声明。"""
        if _TOOL_NAME_PATTERN.fullmatch(self.name) is None:
            raise AgentKitError(
                ErrorCode.INVALID_TOOL_DEFINITION,
                "工具名只允许字母、数字、下划线和短横线",
                http_status=400,
                details={"tool_name": self.name},
            )
        if not isinstance(self.input_model, type) or not issubclass(
            self.input_model,
            BaseModel,
        ):
            raise AgentKitError(
                ErrorCode.INVALID_TOOL_DEFINITION,
                "工具输入 Schema 必须是 Pydantic 模型",
                http_status=400,
                details={"tool_name": self.name},
            )
        input_schema = self.input_schema_override or self.input_model.model_json_schema()
        if input_schema.get("type") != "object":
            raise AgentKitError(
                ErrorCode.INVALID_TOOL_DEFINITION,
                "工具输入 Schema 顶层必须是 object",
                http_status=400,
                details={"tool_name": self.name},
            )
        function_schema: dict[str, JsonValue] = {
            "name": self.name,
            "description": self.description,
            "parameters": cast(JsonValue, input_schema),
        }
        return {"type": "function", "function": function_schema}
