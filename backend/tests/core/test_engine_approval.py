import asyncio
from pathlib import Path

from pydantic import BaseModel
from tests.fakes import FixedEstimator, RecordingEventPublisher, ScriptedModelProvider

from prism_agent_kit.core.context import ContextAssembler
from prism_agent_kit.core.engine import EngineContext, SimpleAgentEngine
from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.models import Message, Run
from prism_agent_kit.core.ports import ModelResponse, ToolCallDraft
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolDefinition
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.testing import echo_tool


class WriteInput(BaseModel):
    path: str
    content: str


class FakeLocator:
    """返回固定根目录的工作区定位器。"""

    def __init__(self, root: Path | None) -> None:
        self.root = root

    async def root_for(self, workspace_id: str | None) -> Path | None:
        return self.root if workspace_id is not None else None

    async def search(self, workspace_id: str, query: str, *, limit: int = 20) -> list[object]:
        return []


def write_tool(root: Path) -> ToolDefinition:
    async def handler(raw: WriteInput, _context: object) -> dict[str, object]:
        (root / raw.path).write_text(raw.content, encoding="utf-8")
        return {"path": raw.path}

    return ToolDefinition(
        name="file_write",
        description="write file",
        input_model=WriteInput,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=5,
        requires_approval=True,
        handler=handler,
    )


def make_engine(
    uow_factory: UnitOfWorkFactory,
    provider: ScriptedModelProvider,
    publisher: RecordingEventPublisher,
    locator: FakeLocator,
    *,
    require_approval: bool = True,
) -> SimpleAgentEngine:
    registry = ToolRegistry()
    registry.register(echo_tool())
    registry.register(write_tool(locator.root or Path("/tmp")))
    return SimpleAgentEngine(
        uow_factory=uow_factory,
        model_provider=provider,
        tool_registry=registry,
        tool_executor=LocalToolExecutor(),
        context_assembler=ContextAssembler(
            FixedEstimator(),
            context_window=100,
            max_output_tokens=10,
            safety_margin_tokens=1,
        ),
        event_publisher=publisher,
        max_steps=5,
        max_output_tokens=100,
        remote_tool_timeout_seconds=300,
        workspace_locator=locator,
        require_write_approval=require_approval,
        approval_timeout_seconds=1800,
    )


async def seed_running_run(uow_factory: UnitOfWorkFactory, workspace_id: str | None = None) -> Run:
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
                workspace_id=workspace_id,
            )
        )
        await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.USER, content="hello")
        )
        await uow.commit()
    async with uow_factory() as uow:
        claimed = await uow.runs.claim_next()
        await uow.commit()
    assert claimed is not None
    return claimed


def tool_response(*drafts: ToolCallDraft) -> ModelResponse:
    return ModelResponse(text="", reasoning=None, tool_calls=list(drafts))


async def test_engine_suspends_for_approval(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    from prism_agent_kit.core.workspace import Workspace

    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path)))
        await uow.commit()
    run = await seed_running_run(uow_factory, workspace.id)
    provider = ScriptedModelProvider(
        [
            tool_response(
                ToolCallDraft(
                    call_id="c1", tool_name="file_write", input={"path": "a.md", "content": "hi"}
                )
            )
        ]
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher, FakeLocator(tmp_path))

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "waiting_for_approval"
    async with uow_factory() as uow:
        refreshed = await uow.runs.get(run.id)
        calls = await uow.tool_calls.list_for_run(run.id)
        assert refreshed.status is RunStatus.WAITING_FOR_APPROVAL
        assert [call.status for call in calls] == [ToolCallStatus.AWAITING_APPROVAL]
        events = await uow.events.list_after(run.id, after_id=0)
        types = [event.event_type for event in events]
        assert EventType.RUN_WAITING_FOR_APPROVAL in types
        assert EventType.TOOL_APPROVAL_REQUIRED in types
        assert EventType.TOOL_COMPLETED not in types
    assert not (tmp_path / "a.md").exists()


async def test_mixed_turn_executes_normal_tool_first(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    from prism_agent_kit.core.workspace import Workspace

    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path)))
        await uow.commit()
    run = await seed_running_run(uow_factory, workspace.id)
    provider = ScriptedModelProvider(
        [
            tool_response(
                ToolCallDraft(call_id="c1", tool_name="echo", input={"text": "one"}),
                ToolCallDraft(
                    call_id="c2", tool_name="file_write", input={"path": "a.md", "content": "hi"}
                ),
            )
        ]
    )
    engine = make_engine(uow_factory, provider, RecordingEventPublisher(), FakeLocator(tmp_path))

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "waiting_for_approval"
    async with uow_factory() as uow:
        calls = {call.id: call for call in await uow.tool_calls.list_for_run(run.id)}
        assert calls["c1"].status is ToolCallStatus.SUCCEEDED
        assert calls["c2"].status is ToolCallStatus.AWAITING_APPROVAL


async def test_approval_disabled_executes_inline(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    from prism_agent_kit.core.workspace import Workspace

    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path)))
        await uow.commit()
    run = await seed_running_run(uow_factory, workspace.id)
    provider = ScriptedModelProvider(
        [
            tool_response(
                ToolCallDraft(
                    call_id="c1", tool_name="file_write", input={"path": "a.md", "content": "hi"}
                )
            ),
            ModelResponse(text="done", reasoning=None, tool_calls=[]),
        ]
    )
    engine = make_engine(
        uow_factory,
        provider,
        RecordingEventPublisher(),
        FakeLocator(tmp_path),
        require_approval=False,
    )

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "completed"
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "hi"


async def test_tool_requested_event_redacts_write_content(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    """file_write 的正文不得进入持久 tool.requested 事件。"""
    from prism_agent_kit.core.workspace import Workspace

    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path)))
        await uow.commit()
    run = await seed_running_run(uow_factory, workspace.id)
    provider = ScriptedModelProvider(
        [
            tool_response(
                ToolCallDraft(
                    call_id="c1",
                    tool_name="file_write",
                    input={"path": "a.md", "content": "secret-body"},
                ),
                ToolCallDraft(call_id="c2", tool_name="echo", input={"text": "one"}),
            )
        ]
    )
    engine = make_engine(uow_factory, provider, RecordingEventPublisher(), FakeLocator(tmp_path))

    await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    async with uow_factory() as uow:
        events = await uow.events.list_after(run.id, after_id=0)
    requested = [event for event in events if event.event_type is EventType.TOOL_REQUESTED]
    write_payload = next(
        payload for event in requested for payload in [event.payload] if payload["call_id"] == "c1"
    )
    assert "content" not in write_payload
    assert write_payload["bytes"] == len("secret-body")
    echo_payload = next(
        payload for event in requested for payload in [event.payload] if payload["call_id"] == "c2"
    )
    assert echo_payload["input"] == {"text": "one"}
