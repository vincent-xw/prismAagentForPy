from datetime import UTC, datetime
from typing import Literal, cast

from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    IndexStatus,
    MessageKind,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.mcp import McpServer, McpStatus
from prism_agent_kit.core.models import (
    CompactionCheckpoint,
    Message,
    ModelProfile,
    Run,
    RunEvent,
    Session,
    ToolCall,
)
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.db.models import (
    CompactionCheckpointRow,
    McpServerRow,
    MessageRow,
    ModelProfileRow,
    RunEventRow,
    RunRow,
    SessionRow,
    ToolCallRow,
    WorkspaceRow,
)


def _to_storage(value: datetime) -> datetime:
    """统一把时间转换为 SQLite 友好的 UTC 无时区值。"""
    return value.astimezone(UTC).replace(tzinfo=None)


def _from_storage(value: datetime) -> datetime:
    """从 SQLite 读出的时间一律恢复为 UTC 时区。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_to_storage(value: datetime | None) -> datetime | None:
    return None if value is None else _to_storage(value)


def _optional_from_storage(value: datetime | None) -> datetime | None:
    return None if value is None else _from_storage(value)


def session_to_row(session: Session) -> SessionRow:
    """把 Session 领域模型转换为 ORM 行。"""
    return SessionRow(
        id=session.id,
        title=session.title,
        workspace_id=session.workspace_id,
        created_at=_to_storage(session.created_at),
        updated_at=_to_storage(session.updated_at),
    )


def session_to_domain(row: SessionRow) -> Session:
    """把 Session ORM 行转换为领域模型。"""
    return Session(
        id=row.id,
        title=row.title,
        workspace_id=row.workspace_id,
        created_at=_from_storage(row.created_at),
        updated_at=_from_storage(row.updated_at),
    )


def run_to_row(run: Run) -> RunRow:
    """把 Run 领域模型转换为 ORM 行。"""
    return RunRow(
        id=run.id,
        session_id=run.session_id,
        workspace_id=run.workspace_id,
        status=run.status.value,
        input_text=run.input_text,
        prompt_name=run.prompt_name,
        prompt_version=run.prompt_version,
        system_prompt=run.system_prompt,
        model=run.model,
        model_profile_id=run.model_profile_id,
        model_context_window=run.model_context_window,
        model_max_output_tokens=run.model_max_output_tokens,
        skill_name=run.skill_name,
        step_count=run.step_count,
        output_text=run.output_text,
        error_code=run.error_code,
        error_message=run.error_message,
        cancel_requested_at=_optional_to_storage(run.cancel_requested_at),
        created_at=_to_storage(run.created_at),
        started_at=_optional_to_storage(run.started_at),
        finished_at=_optional_to_storage(run.finished_at),
    )


def run_to_domain(row: RunRow) -> Run:
    """把 Run ORM 行转换为领域模型。"""
    return Run(
        id=row.id,
        session_id=row.session_id,
        workspace_id=row.workspace_id,
        status=RunStatus(row.status),
        input_text=row.input_text,
        prompt_name=row.prompt_name,
        prompt_version=row.prompt_version,
        system_prompt=row.system_prompt,
        model=row.model,
        model_profile_id=row.model_profile_id,
        model_context_window=row.model_context_window,
        model_max_output_tokens=row.model_max_output_tokens,
        skill_name=row.skill_name,
        step_count=row.step_count,
        output_text=row.output_text,
        error_code=row.error_code,
        error_message=row.error_message,
        cancel_requested_at=_optional_from_storage(row.cancel_requested_at),
        created_at=_from_storage(row.created_at),
        started_at=_optional_from_storage(row.started_at),
        finished_at=_optional_from_storage(row.finished_at),
    )


def message_to_row(message: Message) -> MessageRow:
    """把 Message 领域模型转换为 ORM 行。"""
    row = MessageRow(
        session_id=message.session_id,
        run_id=message.run_id,
        role=message.role.value,
        kind=message.kind.value,
        content=message.content,
        reasoning=message.reasoning,
        tool_call_id=message.tool_call_id,
        created_at=_to_storage(message.created_at),
    )
    if message.id is not None:
        row.id = message.id
    return row


def message_to_domain(row: MessageRow) -> Message:
    """把 Message ORM 行转换为领域模型。"""
    return Message(
        id=row.id,
        session_id=row.session_id,
        run_id=row.run_id,
        role=MessageRole(row.role),
        kind=MessageKind(row.kind),
        content=row.content,
        reasoning=row.reasoning,
        tool_call_id=row.tool_call_id,
        created_at=_from_storage(row.created_at),
    )


def tool_call_to_row(tool_call: ToolCall) -> ToolCallRow:
    """把 ToolCall 领域模型转换为 ORM 行。"""
    return ToolCallRow(
        id=tool_call.id,
        run_id=tool_call.run_id,
        assistant_message_id=tool_call.assistant_message_id,
        tool_name=tool_call.tool_name,
        execution_mode=tool_call.execution_mode.value,
        status=tool_call.status.value,
        input=tool_call.input,
        output=tool_call.output,
        input_digest=tool_call.input_digest,
        error_code=tool_call.error_code,
        error_message=tool_call.error_message,
        expires_at=_optional_to_storage(tool_call.expires_at),
        created_at=_to_storage(tool_call.created_at),
        finished_at=_optional_to_storage(tool_call.finished_at),
    )


def tool_call_to_domain(row: ToolCallRow) -> ToolCall:
    """把 ToolCall ORM 行转换为领域模型。"""
    return ToolCall(
        id=row.id,
        run_id=row.run_id,
        assistant_message_id=row.assistant_message_id,
        tool_name=row.tool_name,
        execution_mode=ExecutionMode(row.execution_mode),
        status=ToolCallStatus(row.status),
        input=row.input,
        output=row.output,
        input_digest=row.input_digest,
        error_code=row.error_code,
        error_message=row.error_message,
        expires_at=_optional_from_storage(row.expires_at),
        created_at=_from_storage(row.created_at),
        finished_at=_optional_from_storage(row.finished_at),
    )


def run_event_to_row(event: RunEvent) -> RunEventRow:
    """把 RunEvent 领域模型转换为 ORM 行。"""
    row = RunEventRow(
        run_id=event.run_id,
        event_type=event.event_type.value,
        payload=event.payload,
        created_at=_to_storage(event.created_at),
    )
    if event.id is not None:
        row.id = event.id
    return row


def run_event_to_domain(row: RunEventRow) -> RunEvent:
    """把 RunEvent ORM 行转换为领域模型。"""
    return RunEvent(
        id=row.id,
        run_id=row.run_id,
        event_type=EventType(row.event_type),
        payload=row.payload,
        created_at=_from_storage(row.created_at),
    )


def workspace_to_row(workspace: Workspace) -> WorkspaceRow:
    """把 Workspace 领域模型转换为 ORM 行。"""
    return WorkspaceRow(
        id=workspace.id,
        root_path=workspace.root_path,
        label=workspace.label,
        name=workspace.name,
        user=workspace.user,
        permission_mode=workspace.permission_mode,
        is_active=1 if workspace.is_active else 0,
        index_status=workspace.index_status.value,
        index_error=workspace.index_error,
        file_count=workspace.file_count,
        indexed_at=_optional_to_storage(workspace.indexed_at),
        created_at=_to_storage(workspace.created_at),
        updated_at=_to_storage(workspace.updated_at),
    )


def workspace_to_domain(row: WorkspaceRow) -> Workspace:
    """把 Workspace ORM 行转换为领域模型。"""
    return Workspace(
        id=row.id,
        root_path=row.root_path,
        label=row.label,
        name=row.name,
        user=row.user,
        permission_mode=row.permission_mode or "workspace_write",
        is_active=row.is_active == 1,
        index_status=IndexStatus(row.index_status),
        index_error=row.index_error,
        file_count=row.file_count,
        indexed_at=_optional_from_storage(row.indexed_at),
        created_at=_from_storage(row.created_at),
        updated_at=_from_storage(row.updated_at),
    )


def mcp_server_to_row(server: McpServer) -> McpServerRow:
    """把 McpServer 领域模型转换为 ORM 行。"""
    return McpServerRow(
        id=server.id,
        name=server.name,
        transport=server.transport,
        command=server.command,
        args_json=server.args,
        env_json=server.env,
        url=server.url,
        headers_json=server.headers,
        enabled=1 if server.enabled else 0,
        status=server.status.value,
        last_error=server.last_error,
        created_at=_to_storage(server.created_at),
        updated_at=_to_storage(server.updated_at),
    )


def mcp_server_to_domain(row: McpServerRow) -> McpServer:
    """把 McpServer ORM 行转换为领域模型。"""
    return McpServer(
        id=row.id,
        name=row.name,
        transport=cast(Literal["stdio", "http"], row.transport),
        command=row.command,
        args=list(row.args_json or []),
        env=dict(row.env_json or {}),
        url=row.url,
        headers=dict(row.headers_json or {}),
        enabled=row.enabled == 1,
        status=McpStatus(row.status),
        last_error=row.last_error,
        created_at=_from_storage(row.created_at),
        updated_at=_from_storage(row.updated_at),
    )


def model_profile_to_row(profile: ModelProfile) -> ModelProfileRow:
    """把 ModelProfile 转换为 ORM 行。"""
    return ModelProfileRow(
        id=profile.id,
        name=profile.name,
        base_url=profile.base_url,
        model=profile.model,
        api_key_env=profile.api_key_env,
        api_key=profile.api_key,
        context_window=profile.context_window,
        max_output_tokens=profile.max_output_tokens,
        is_active=1 if profile.is_active else 0,
        created_at=_to_storage(profile.created_at),
        updated_at=_to_storage(profile.updated_at),
    )


def model_profile_to_domain(row: ModelProfileRow) -> ModelProfile:
    """把 ModelProfile ORM 行转换为领域模型。"""
    return ModelProfile(
        id=row.id,
        name=row.name,
        base_url=row.base_url,
        model=row.model,
        api_key_env=row.api_key_env,
        api_key=row.api_key,
        context_window=row.context_window,
        max_output_tokens=row.max_output_tokens,
        is_active=row.is_active == 1,
        created_at=_from_storage(row.created_at),
        updated_at=_from_storage(row.updated_at),
    )


def checkpoint_to_row(checkpoint: CompactionCheckpoint) -> CompactionCheckpointRow:
    """把 CompactionCheckpoint 转换为 ORM 行。"""
    return CompactionCheckpointRow(
        id=checkpoint.id,
        session_id=checkpoint.session_id,
        summary=checkpoint.summary,
        first_kept_message_id=checkpoint.first_kept_message_id,
        tokens_before=checkpoint.tokens_before,
        tokens_after=checkpoint.tokens_after,
        pruned_chars=checkpoint.pruned_chars,
        created_at=_to_storage(checkpoint.created_at),
    )


def checkpoint_to_domain(row: CompactionCheckpointRow) -> CompactionCheckpoint:
    """把 CompactionCheckpoint ORM 行转换为领域模型。"""
    return CompactionCheckpoint(
        id=row.id,
        session_id=row.session_id,
        summary=row.summary,
        first_kept_message_id=row.first_kept_message_id,
        tokens_before=row.tokens_before,
        tokens_after=row.tokens_after,
        pruned_chars=row.pruned_chars,
        created_at=_from_storage(row.created_at),
    )
