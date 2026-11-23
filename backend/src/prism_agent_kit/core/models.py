from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, JsonValue

from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(UTC)


class Session(BaseModel):
    """连续对话上下文的领域模型。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str | None = None
    workspace_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Run(BaseModel):
    """一次用户输入触发的完整 Agent 执行。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    workspace_id: str | None = None
    status: RunStatus = RunStatus.QUEUED
    input_text: str
    prompt_name: str
    prompt_version: str
    system_prompt: str
    model: str
    step_count: int = 0
    output_text: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancel_requested_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def prompt_ref(self) -> str:
        """返回可直接用于展示与查找的 Prompt 引用。"""
        return f"{self.prompt_name}@{self.prompt_version}"


class Message(BaseModel):
    """模型可见历史中的一条消息。"""

    id: int | None = None
    session_id: str
    run_id: str
    role: MessageRole
    content: JsonValue
    reasoning: str | None = None
    tool_call_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ToolCall(BaseModel):
    """模型发起或 Core 生成的一次工具调用。"""

    id: str
    run_id: str
    assistant_message_id: int
    tool_name: str
    execution_mode: ExecutionMode
    status: ToolCallStatus = ToolCallStatus.PENDING
    input: JsonValue
    output: JsonValue = None
    input_digest: str
    error_code: str | None = None
    error_message: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class RunEvent(BaseModel):
    """可重放的产品事件与状态事实。"""

    id: int | None = None
    run_id: str
    event_type: EventType
    payload: JsonValue
    created_at: datetime = Field(default_factory=utc_now)
