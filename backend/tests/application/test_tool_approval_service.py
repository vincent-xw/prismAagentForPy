from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel
from tests.fakes import RecordingEventPublisher

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.tool_approval_service import ToolApprovalService
from prism_agent_kit.application.tool_result_recorder import ToolResultRecorder
from prism_agent_kit.application.workspace_service import WorkspaceService
from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import ExecutionMode, MessageRole, RunStatus, ToolCallStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run, ToolCall, utc_now
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolDefinition
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.testing import wait_for_host_tool
from prism_agent_kit.tools.workspace_tools import build_workspace_tools


@dataclass
class ApprovalContext:
    service: ToolApprovalService
    run_id: str
    call_id: str
    workspace_root: Path


class RecordingIndexTasks:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def submit(
        self, workspace_id: str, *, mode: str = "full", rel_path: str | None = None
    ) -> None:
        self.calls.append((mode, workspace_id, rel_path))


class GenericInput(BaseModel):
    query: str


async def _generic_handler(raw: GenericInput, _context: object) -> dict[str, object]:
    return {"echo": raw.query}


def _generic_tool() -> ToolDefinition:
    return ToolDefinition(
        name="mcp__demo__search",
        description="generic mcp tool",
        input_model=GenericInput,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=5,
        requires_approval=True,
        handler=_generic_handler,
    )


def build_service(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> ToolApprovalService:
    registry = ToolRegistry()
    for tool in build_workspace_tools():
        registry.register(tool)
    registry.register(wait_for_host_tool())
    registry.register(_generic_tool())
    publisher = RecordingEventPublisher()
    workspace_service = WorkspaceService(
        uow_factory=uow_factory,
        index_tasks=RecordingIndexTasks(),
        data_dir=tmp_path / "app-data",
    )
    return ToolApprovalService(
        uow_factory=uow_factory,
        tool_registry=registry,
        tool_executor=LocalToolExecutor(),
        tool_result_recorder=ToolResultRecorder(uow_factory=uow_factory, event_publisher=publisher),
        workspace_service=workspace_service,
        index_tasks=RecordingIndexTasks(),
        event_publisher=publisher,
        cancellation_registry=RunCancellationRegistry(),
    )


async def seed_workspace(uow_factory: UnitOfWorkFactory, root: Path) -> Workspace:
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(root)))
        await uow.commit()
    return workspace


async def seed_approval(
    uow_factory: UnitOfWorkFactory,
    workspace: Workspace,
    *,
    write_path: str = "notes.md",
    content: str = "hello",
    with_remote: bool = False,
    expires_in: int = 1800,
) -> tuple[str, str, str | None]:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        run = await uow.runs.create(
            Run(
                session_id=session.id,
                input_text="hello",
                prompt_name="default",
                prompt_version="1",
                system_prompt="system",
                model="test-model",
                workspace_id=workspace.id,
            )
        )
        await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.USER, content="hello")
        )
        await uow.commit()
    async with uow_factory() as uow:
        await uow.runs.claim_next()
        assistant = await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.ASSISTANT, content="")
        )
        assert assistant.id is not None
        write_input = {"path": write_path, "content": content, "mode": "overwrite"}
        calls = await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-write",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="file_write",
                    execution_mode=ExecutionMode.LOCAL,
                    input=write_input,
                    input_digest=canonical_json_digest(write_input),
                )
            ]
        )
        remote_id = None
        if with_remote:
            remote_input = {"value": "one"}
            remote = await uow.tool_calls.create_many(
                [
                    ToolCall(
                        id="call-remote",
                        run_id=run.id,
                        assistant_message_id=assistant.id,
                        tool_name="wait_for_host",
                        execution_mode=ExecutionMode.REMOTE,
                        input=remote_input,
                        input_digest=canonical_json_digest(remote_input),
                        expires_at=utc_now() + timedelta(minutes=5),
                    )
                ]
            )
            remote_id = remote[0].id
        await uow.tool_calls.await_call(
            run.id, calls[0].id, utc_now() + timedelta(seconds=expires_in)
        )
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_APPROVAL)
        await uow.commit()
        return run.id, calls[0].id, remote_id


async def test_approve_executes_write_and_requeues(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id, _ = await seed_approval(uow_factory, workspace)

    call, run = await service.decide(run_id, call_id, "approve")

    assert call.status is ToolCallStatus.SUCCEEDED
    assert run.status is RunStatus.QUEUED
    assert (root / "notes.md").read_text(encoding="utf-8") == "hello"


async def test_reject_marks_tool_rejected(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id, _ = await seed_approval(uow_factory, workspace)

    call, run = await service.decide(run_id, call_id, "reject", "不要写")

    assert call.status is ToolCallStatus.FAILED
    assert call.error_code == ErrorCode.TOOL_REJECTED.value
    assert run.status is RunStatus.QUEUED
    assert not (root / "notes.md").exists()


async def test_mixed_turn_moves_to_waiting_for_tool(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id, _ = await seed_approval(uow_factory, workspace, with_remote=True)

    _, run = await service.decide(run_id, call_id, "approve")

    assert run.status is RunStatus.WAITING_FOR_TOOL


async def test_write_uses_run_workspace_after_switch(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id, _ = await seed_approval(uow_factory, workspace)

    # 审批前切换活跃工作区到另一个目录
    await service._workspace_service.create(str(other))
    call, _ = await service.decide(run_id, call_id, "approve")

    assert call.status is ToolCallStatus.SUCCEEDED
    assert (root / "notes.md").exists()
    assert not (other / "notes.md").exists()


async def test_partial_approvals_keep_waiting(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id, _ = await seed_approval(uow_factory, workspace)
    # 追加第二个待审批调用
    async with uow_factory() as uow:
        run = await uow.runs.get(run_id)
        calls = await uow.tool_calls.list_for_run(run_id)
        assistant_id = calls[0].assistant_message_id
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-write-2",
                    run_id=run_id,
                    assistant_message_id=assistant_id,
                    tool_name="file_write",
                    execution_mode=ExecutionMode.LOCAL,
                    input={"path": "second.md", "content": "2", "mode": "overwrite"},
                    input_digest=canonical_json_digest({"path": "second.md"}),
                )
            ]
        )
        await uow.tool_calls.await_call(run_id, "call-write-2", utc_now() + timedelta(seconds=60))
        await uow.commit()

    _, run = await service.decide(run_id, call_id, "approve")

    assert run.status is RunStatus.WAITING_FOR_APPROVAL


async def test_preview_contains_diff(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "notes.md").write_text("old line", encoding="utf-8")
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id, _ = await seed_approval(uow_factory, workspace, content="new line")

    preview = await service.preview(run_id, call_id)

    assert preview.exists is True
    assert preview.diff is not None
    assert "-old line" in preview.diff
    assert "+new line" in preview.diff


async def test_expired_approval_rejected(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id, _ = await seed_approval(uow_factory, workspace, expires_in=-10)

    with pytest.raises(AgentKitError) as error:
        await service.decide(run_id, call_id, "approve")
    assert error.value.code is ErrorCode.TOOL_CALL_EXPIRED


async def seed_generic_approval(
    uow_factory: UnitOfWorkFactory, workspace: Workspace
) -> tuple[str, str]:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        run = await uow.runs.create(
            Run(
                session_id=session.id,
                input_text="hello",
                prompt_name="default",
                prompt_version="1",
                system_prompt="system",
                model="test-model",
                workspace_id=workspace.id,
            )
        )
        await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.USER, content="hello")
        )
        await uow.commit()
    async with uow_factory() as uow:
        await uow.runs.claim_next()
        assistant = await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.ASSISTANT, content="")
        )
        assert assistant.id is not None
        payload = {"query": "订单 123"}
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-generic",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="mcp__demo__search",
                    execution_mode=ExecutionMode.LOCAL,
                    input=payload,
                    input_digest=canonical_json_digest(payload),
                )
            ]
        )
        await uow.tool_calls.await_call(run.id, "call-generic", utc_now() + timedelta(seconds=600))
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_APPROVAL)
        await uow.commit()
        return run.id, "call-generic"


async def test_generic_tool_approval_has_no_file_fields(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace = await seed_workspace(uow_factory, root)
    service = build_service(uow_factory, tmp_path)
    run_id, call_id = await seed_generic_approval(uow_factory, workspace)

    preview = await service.preview(run_id, call_id)
    assert preview.kind == "generic"
    assert preview.diff is None
    assert preview.input_preview is not None and "订单 123" in preview.input_preview

    call, run = await service.decide(run_id, call_id, "approve")
    assert call.status is ToolCallStatus.SUCCEEDED
    assert call.output == {"echo": "订单 123"}
    assert run.status is RunStatus.QUEUED
