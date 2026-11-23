from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, JsonValue

from prism_agent_kit.core.enums import EventType
from prism_agent_kit.core.models import Message, ToolCall, utc_now


class ToolCallDraft(BaseModel):
    """模型返回、尚未落库的工具调用。"""

    call_id: str
    tool_name: str
    input: JsonValue


class TokenUsage(BaseModel):
    """模型返回的 token 用量。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ModelChunk(BaseModel):
    """模型流式增量。仅用于 SSE 临时事件。"""

    text: str = ""
    reasoning: str = ""


class ModelRequest(BaseModel):
    """一次模型请求所需的完整输入。"""

    system_prompt: str
    messages: list[Message]
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tools: list[dict[str, JsonValue]] = Field(default_factory=list)
    max_output_tokens: int | None = None


class ModelResponse(BaseModel):
    """模型流结束后的聚合结果。"""

    text: str = ""
    reasoning: str | None = None
    tool_calls: list[ToolCallDraft] = Field(default_factory=list)
    usage: TokenUsage | None = None


class ModelProvider(Protocol):
    """可替换的模型 Provider 端口。"""

    async def stream(
        self,
        request: ModelRequest,
        on_delta: Callable[[ModelChunk], Awaitable[None]] | None = None,
    ) -> ModelResponse: ...


class EventEnvelope(BaseModel):
    """交给事件总线或 SSE 的统一事件信封。"""

    event_id: int | None = None
    run_id: str
    event_type: EventType
    payload: JsonValue
    created_at: datetime = Field(default_factory=utc_now)


class EventPublisher(Protocol):
    """事务提交后发布事件的端口。"""

    async def publish(self, event: EventEnvelope) -> None: ...


class WorkspaceLocator(Protocol):
    """Run 绑定的工作区定位与检索接口。"""

    async def root_for(self, workspace_id: str | None) -> Path | None: ...

    async def search(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[Any]: ...
