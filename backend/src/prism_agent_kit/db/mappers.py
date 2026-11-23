from datetime import UTC, datetime

from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.enums import IndexStatus
from prism_agent_kit.core.models import Message, Run, RunEvent, Session, ToolCall
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.db.models import (
    MessageRow,
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
        created_at=_to_storage(session.created_at),
        updated_at=_to_storage(session.updated_at),
    )


def session_to_domain(row: SessionRow) -> Session:
    """把 Session ORM 行转换为领域模型。"""
    return Session(
        id=row.id,
        title=row.title,
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
        is_active=row.is_active == 1,
        index_status=IndexStatus(row.index_status),
        index_error=row.index_error,
        file_count=row.file_count,
        indexed_at=_optional_from_storage(row.indexed_at),
        created_at=_from_storage(row.created_at),
        updated_at=_from_storage(row.updated_at),
    )
