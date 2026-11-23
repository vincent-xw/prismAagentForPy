from datetime import datetime

from pydantic import BaseModel, Field, JsonValue, field_validator

from prism_agent_kit.core.enums import ExecutionMode, MessageRole, RunStatus, ToolCallStatus
from prism_agent_kit.core.models import Message, Run, Session, ToolCall
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.tools.contracts import ToolDefinition


class SessionCreate(BaseModel):
    """创建 Session 的请求。"""

    title: str | None = Field(default=None, max_length=255)


class SessionWorkspaceUpdate(BaseModel):
    """会话绑定工作区请求；workspace_id 为空表示解绑。"""

    workspace_id: str | None = None


class SessionView(BaseModel):
    """对外返回的 Session 视图。"""

    id: str
    title: str | None
    workspace_id: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, session: Session) -> "SessionView":
        return cls(
            id=session.id,
            title=session.title,
            workspace_id=session.workspace_id,
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
    workspace_id: str | None
    status: RunStatus
    input: str
    prompt_ref: str
    model: str
    step_count: int
    output: str | None
    error_code: str | None
    error_message: str | None
    cancel_requested_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, run: Run) -> "RunView":
        return cls(
            id=run.id,
            session_id=run.session_id,
            workspace_id=run.workspace_id,
            status=run.status,
            input=run.input_text,
            prompt_ref=run.prompt_ref,
            model=run.model,
            step_count=run.step_count,
            output=run.output_text,
            error_code=run.error_code,
            error_message=run.error_message,
            cancel_requested_at=run.cancel_requested_at,
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


class ToolResultErrorPayload(BaseModel):
    """远端工具失败结果。"""

    code: str
    message: str


class ToolResultRequest(BaseModel):
    """远端宿主回填工具结果的请求。"""

    ok: bool
    input_digest: str
    output: JsonValue = None
    error: ToolResultErrorPayload | None = None


class ToolCallView(BaseModel):
    """对外返回的 ToolCall 视图。"""

    id: str
    run_id: str
    tool_name: str
    status: ToolCallStatus
    output: JsonValue
    error_code: str | None
    error_message: str | None
    expires_at: datetime | None

    @classmethod
    def from_domain(cls, call: ToolCall) -> "ToolCallView":
        return cls(
            id=call.id,
            run_id=call.run_id,
            tool_name=call.tool_name,
            status=call.status,
            output=call.output,
            error_code=call.error_code,
            error_message=call.error_message,
            expires_at=call.expires_at,
        )


class ToolView(BaseModel):
    """工具发现结果。"""

    name: str
    description: str
    execution_mode: ExecutionMode
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue] | None

    @classmethod
    def from_domain(cls, definition: ToolDefinition) -> "ToolView":
        output_schema = (
            definition.output_model.model_json_schema()
            if definition.output_model is not None
            else None
        )
        return cls(
            name=definition.name,
            description=definition.description,
            execution_mode=definition.execution_mode,
            input_schema=definition.input_model.model_json_schema(),
            output_schema=output_schema,
        )


class ToolListResponse(BaseModel):
    """工具列表响应。"""

    items: list[ToolView]


class WorkspaceView(BaseModel):
    """对外返回的工作区视图。"""

    id: str
    root_path: str
    label: str | None
    is_active: bool
    index_status: str
    index_error: str | None
    file_count: int
    indexed_at: datetime | None

    @classmethod
    def from_domain(cls, workspace: "Workspace") -> "WorkspaceView":
        return cls(
            id=workspace.id,
            root_path=workspace.root_path,
            label=workspace.label,
            is_active=workspace.is_active,
            index_status=workspace.index_status.value,
            index_error=workspace.index_error,
            file_count=workspace.file_count,
            indexed_at=workspace.indexed_at,
        )


class WorkspaceListResponse(BaseModel):
    """工作区列表。"""

    items: list[WorkspaceView]
    active_id: str | None


class WorkspaceCreate(BaseModel):
    """绑定工作区请求。"""

    path: str
    label: str | None = Field(default=None, max_length=255)


class WorkspacePickResponse(BaseModel):
    """原生目录选择结果。"""

    path: str


class TreeEntryView(BaseModel):
    """目录项视图。"""

    name: str
    type: str
    size: int | None = None
    modified_at: float | None = None


class TreeResponse(BaseModel):
    """目录列表。"""

    items: list[TreeEntryView]


class FileView(BaseModel):
    """文件读取视图。"""

    path: str
    content: str
    truncated: bool
    size: int


class SearchHitView(BaseModel):
    """检索命中视图。"""

    path: str
    snippet: str


class SearchResponse(BaseModel):
    """检索结果。"""

    items: list[SearchHitView]


class ApprovalRequest(BaseModel):
    """审批请求。"""

    decision: str
    reason: str | None = Field(default=None, max_length=200)


class ApprovalPreviewView(BaseModel):
    """审批预览视图。"""

    path: str
    mode: str
    bytes: int
    exists: bool
    diff: str | None
    truncated: bool


class ApprovalResponse(BaseModel):
    """审批结果，同时返回调用与 Run 的最新状态。"""

    call: ToolCallView
    run: RunView
