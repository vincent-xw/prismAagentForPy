import asyncio

import pytest
from pydantic import BaseModel
from tests.fakes import (
    FixedEstimator,
    RecordingEventPublisher,
    ScriptedModelProvider,
)

from prism_agent_kit.application.tool_result_service import (
    RemoteToolError,
    RemoteToolResult,
    ToolResultService,
)
from prism_agent_kit.core.context import ContextAssembler
from prism_agent_kit.core.engine import EngineContext, SimpleAgentEngine
from prism_agent_kit.core.enums import (
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run
from prism_agent_kit.core.ports import ModelResponse, ToolCallDraft
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolDefinition
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.testing import wait_for_host_tool


class SchemaOutput(BaseModel):
    value: str


class EmptyInput(BaseModel):
    pass


def schema_remote_tool() -> ToolDefinition:
    """返回带输出 Schema 的远端测试工具。"""
    return ToolDefinition(
        name="schema_remote",
        description="需要结构化输出的远端工具",
        input_model=EmptyInput,
        output_model=SchemaOutput,
        execution_mode=ExecutionMode.REMOTE,
        timeout_seconds=300,
    )


def make_engine(
    uow_factory: UnitOfWorkFactory,
    provider: ScriptedModelProvider,
    publisher: RecordingEventPublisher,
    registry: ToolRegistry,
    *,
    remote_timeout_seconds: float = 300,
) -> SimpleAgentEngine:
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
        max_steps=10,
        max_output_tokens=100,
        remote_tool_timeout_seconds=remote_timeout_seconds,
    )


async def seed_run(uow_factory: UnitOfWorkFactory) -> Run:
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
            )
        )
        await uow.messages.append(
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.USER,
                content="hello",
            )
        )
        await uow.commit()

    async with uow_factory() as uow:
        claimed = await uow.runs.claim_next()
        await uow.commit()
    assert claimed is not None
    return claimed


async def start_remote_run(
    uow_factory: UnitOfWorkFactory,
    call_ids: list[str],
) -> tuple[Run, ToolRegistry, RecordingEventPublisher]:
    """启动一个只请求远端工具的 Run 并返回等待态。"""
    registry = ToolRegistry()
    registry.register(wait_for_host_tool())
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id=call_id,
                        tool_name="wait_for_host",
                        input={"value": call_id},
                    )
                    for call_id in call_ids
                ]
            )
        ]
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher, registry)
    run = await seed_run(uow_factory)

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "waiting_for_tools"
    return run, registry, publisher


async def test_remote_tool_suspends_and_requeues_after_all_results(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run, registry, publisher = await start_remote_run(
        uow_factory,
        ["call-1", "call-2"],
    )
    service = ToolResultService(
        uow_factory=uow_factory,
        tool_registry=registry,
        event_publisher=publisher,
    )

    async with uow_factory() as uow:
        calls = await uow.tool_calls.list_for_run(run.id)
    digests = {call.id: call.input_digest for call in calls}

    first = await service.submit(
        run.id,
        "call-1",
        digests["call-1"],
        RemoteToolResult(ok=True, output={"value": "one"}),
    )
    assert first.status is ToolCallStatus.SUCCEEDED

    async with uow_factory() as uow:
        after_first = await uow.runs.get(run.id)
    assert after_first.status is RunStatus.WAITING_FOR_TOOL

    await service.submit(
        run.id,
        "call-2",
        digests["call-2"],
        RemoteToolResult(ok=True, output={"value": "two"}),
    )

    async with uow_factory() as uow:
        requeued = await uow.runs.get(run.id)
        events = await uow.events.list_after(run.id)
    assert requeued.status is RunStatus.QUEUED
    assert any(event.event_type.value == "run.requeued" for event in events)

    duplicate = await service.submit(
        run.id,
        "call-1",
        digests["call-1"],
        RemoteToolResult(ok=True, output={"value": "one"}),
    )
    assert duplicate.status is ToolCallStatus.SUCCEEDED


async def test_conflicting_digest_does_not_modify_history(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run, registry, publisher = await start_remote_run(uow_factory, ["call-1"])
    service = ToolResultService(
        uow_factory=uow_factory,
        tool_registry=registry,
        event_publisher=publisher,
    )

    with pytest.raises(AgentKitError) as error:
        await service.submit(
            run.id,
            "call-1",
            "sha256:wrong",
            RemoteToolResult(ok=True, output={"value": "one"}),
        )

    assert error.value.code is ErrorCode.TOOL_INPUT_DIGEST_MISMATCH

    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run.id, "call-1")
        stored_run = await uow.runs.get(run.id)
    assert call.status is ToolCallStatus.PENDING
    assert stored_run.status is RunStatus.WAITING_FOR_TOOL


async def test_invalid_remote_output_keeps_call_pending(
    uow_factory: UnitOfWorkFactory,
) -> None:
    registry = ToolRegistry()
    registry.register(schema_remote_tool())
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id="call-1",
                        tool_name="schema_remote",
                        input={},
                    )
                ]
            )
        ]
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher, registry)
    run = await seed_run(uow_factory)
    await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run.id, "call-1")
    service = ToolResultService(
        uow_factory=uow_factory,
        tool_registry=registry,
        event_publisher=publisher,
    )

    with pytest.raises(AgentKitError) as error:
        await service.submit(
            run.id,
            "call-1",
            call.input_digest,
            RemoteToolResult(ok=True, output={"wrong": "shape"}),
        )

    assert error.value.code is ErrorCode.TOOL_OUTPUT_INVALID
    assert error.value.http_status == 422

    async with uow_factory() as uow:
        still_pending = await uow.tool_calls.get(run.id, "call-1")
    assert still_pending.status is ToolCallStatus.PENDING


async def test_expired_result_is_rejected(
    uow_factory: UnitOfWorkFactory,
) -> None:
    registry = ToolRegistry()
    registry.register(wait_for_host_tool())
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id="call-1",
                        tool_name="wait_for_host",
                        input={"value": "one"},
                    )
                ]
            )
        ]
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(
        uow_factory,
        provider,
        publisher,
        registry,
        remote_timeout_seconds=-1,
    )
    run = await seed_run(uow_factory)
    await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run.id, "call-1")
    service = ToolResultService(
        uow_factory=uow_factory,
        tool_registry=registry,
        event_publisher=publisher,
    )

    with pytest.raises(AgentKitError) as error:
        await service.submit(
            run.id,
            "call-1",
            call.input_digest,
            RemoteToolResult(ok=True, output={"value": "late"}),
        )

    assert error.value.code is ErrorCode.TOOL_CALL_EXPIRED


async def test_remote_failure_closes_call_with_host_error(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run, registry, publisher = await start_remote_run(uow_factory, ["call-1"])
    service = ToolResultService(
        uow_factory=uow_factory,
        tool_registry=registry,
        event_publisher=publisher,
    )

    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run.id, "call-1")
    await service.submit(
        run.id,
        "call-1",
        call.input_digest,
        RemoteToolResult(
            ok=False,
            error=RemoteToolError(
                code="BROWSER_ACTION_FAILED",
                message="页面元素不存在",
            ),
        ),
    )

    async with uow_factory() as uow:
        failed = await uow.tool_calls.get(run.id, "call-1")
        stored_run = await uow.runs.get(run.id)
    assert failed.status is ToolCallStatus.FAILED
    assert failed.error_code == "BROWSER_ACTION_FAILED"
    assert stored_run.status is RunStatus.QUEUED


async def test_cancel_closes_every_unfinished_remote_tool_call(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run, registry, publisher = await start_remote_run(
        uow_factory,
        ["call-1", "call-2"],
    )
    provider = ScriptedModelProvider([])
    engine = make_engine(uow_factory, provider, publisher, registry)

    outcome = await engine.cancel(run.id)

    assert outcome.kind == "cancelled"
    async with uow_factory() as uow:
        calls = await uow.tool_calls.list_for_run(run.id)
        messages = await uow.messages.list_for_session(run.session_id)
        stored_run = await uow.runs.get(run.id)

    assert all(call.status is ToolCallStatus.CANCELLED for call in calls)
    assert [message.role for message in messages].count(MessageRole.TOOL) == 2
    assert stored_run.status is RunStatus.CANCELLED
