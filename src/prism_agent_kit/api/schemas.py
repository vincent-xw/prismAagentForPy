from datetime import datetime

from pydantic import BaseModel, Field, JsonValue, field_validator

from prism_agent_kit.core.enums import MessageRole, RunStatus
from prism_agent_kit.core.models import Message, Run, Session


class SessionCreate(BaseModel):
    """创建 Session 的请求。"""

    title: str | None = Field(default=None, max_length=255)


class SessionView(BaseModel):
    """对外返回的 Session 视图。"""

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, session: Session) -> "SessionView":
        return cls(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


class SessionListResponse(BaseModel):
    """Session 列表响应。"""

    items: list[SessionView]


class RunCreate(BaseModel):
    """创建 Run 的请求。"""

    input: str
    prompt_ref: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("input")
    @classmethod
    def validate_non_blank_input(cls, value: str) -> str:
        """拒绝空字符串和仅包含空白的输入。"""
        if not value.strip():
            raise ValueError("input 不能为空")
        return value


class RunView(BaseModel):
    """对外返回的 Run 视图。"""

    id: str
    session_id: str
    status: RunStatus
    input: str
    prompt_ref: str
    model: str
    step_count: int
    output: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, run: Run) -> "RunView":
        return cls(
            id=run.id,
            session_id=run.session_id,
            status=run.status,
            input=run.input_text,
            prompt_ref=run.prompt_ref,
            model=run.model,
            step_count=run.step_count,
            output=run.output_text,
            error_code=run.error_code,
            error_message=run.error_message,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )


class MessageView(BaseModel):
    """对外返回的消息视图。"""

    id: int
    session_id: str
    run_id: str
    role: MessageRole
    content: JsonValue
    reasoning: str | None
    tool_call_id: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, message: Message) -> "MessageView":
        if message.id is None:
            raise ValueError("已持久化消息必须包含 ID")
        return cls(
            id=message.id,
            session_id=message.session_id,
            run_id=message.run_id,
            role=message.role,
            content=message.content,
            reasoning=message.reasoning,
            tool_call_id=message.tool_call_id,
            created_at=message.created_at,
        )


class MessageListResponse(BaseModel):
    """消息列表响应。"""

    items: list[MessageView]
