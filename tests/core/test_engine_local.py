import asyncio

import pytest
from pydantic import BaseModel
from tests.fakes import (
    FixedEstimator,
    RecordingEventPublisher,
    ScriptedModelProvider,
)

from prism_agent_kit.core.context import ContextAssembler
from prism_agent_kit.core.engine import (
    EngineContext,
    SimpleAgentEngine,
)
from prism_agent_kit.core.enums import (
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run
from prism_agent_kit.core.ports import ModelResponse, ToolCallDraft
from prism_agent_kit.db.repositories.runs import RunRepository
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolDefinition, ToolExecutionContext
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.testing import echo_tool


async def seed_running_run(uow_factory: UnitOfWorkFactory) -> Run:
    """创建 Session、Run 和 user Message。以原子 claim 进入 running。"""
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


def make_engine(
    uow_factory: UnitOfWorkFactory,
    provider: ScriptedModelProvider,
    publisher: RecordingEventPublisher,
    *,
    max_steps: int = 10,
    registry: ToolRegistry | None = None,
    tool_timeout_seconds: float | None = None,
) -> SimpleAgentEngine:
    resolved_registry = registry or ToolRegistry()
    if registry is None:
        resolved_registry.register(echo_tool())
    return SimpleAgentEngine(
        uow_factory=uow_factory,
        model_provider=provider,
        tool_registry=resolved_registry,
        tool_executor=LocalToolExecutor(),
        context_assembler=ContextAssembler(
            FixedEstimator(),
            context_window=100,
            max_output_tokens=10,
            safety_margin_tokens=1,
        ),
        event_publisher=publisher,
        max_steps=max_steps,
        max_output_tokens=100,
        remote_tool_timeout_seconds=300,
        tool_timeout_seconds=tool_timeout_seconds,
    )


class ControlledModelProvider:
    """阻塞到测试释放后再返回固定响应。"""

    def __init__(self, response: ModelResponse) -> None:
        self.response = response
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(
        self,
        request: object,
        on_delta: object = None,
    ) -> ModelResponse:
        self.started.set()
        await self.release.wait()
        return self.response


class FailingControlledModelProvider(ControlledModelProvider):
    """等待测试释放后抛出模型错误。"""

    async def stream(
        self,
        request: object,
        on_delta: object = None,
    ) -> ModelResponse:
        self.started.set()
        await self.release.wait()
        from prism_agent_kit.core.errors import AgentKitError, ErrorCode

        raise AgentKitError(
            ErrorCode.MODEL_TIMEOUT,
            "模型请求超时",
            http_status=504,
        )


class SlowInput(BaseModel):
    text: str


class SlowOutput(BaseModel):
    text: str


async def slow_handler(
    input_data: SlowInput,
    context: ToolExecutionContext,
) -> SlowOutput:
    await asyncio.sleep(1)
    return SlowOutput(text=input_data.text)


def slow_tool() -> ToolDefinition:
    return ToolDefinition(
        name="slow",
        description="测试全局工具超时上限",
        input_model=SlowInput,
        output_model=SlowOutput,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=5,
        handler=slow_handler,
    )


async def test_engine_processes_every_tool_call_in_one_assistant_turn(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_running_run(uow_factory)
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id="call-1",
                        tool_name="echo",
                        input={"text": "first"},
                    ),
                    ToolCallDraft(
                        call_id="call-2",
                        tool_name="echo",
                        input={"text": "second"},
                    ),
                ]
            ),
            ModelResponse(text="done"),
        ]
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher)

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "completed"
    assert len(provider.requests) == 2

    async with uow_factory() as uow:
        calls = await uow.tool_calls.list_for_run(run.id)
        messages = await uow.messages.list_for_session(run.session_id)
        stored_run = await uow.runs.get(run.id)

    assert [call.status for call in calls] == [
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.SUCCEEDED,
    ]
    assert [message.role for message in messages].count(MessageRole.TOOL) == 2
    assert stored_run.status is RunStatus.SUCCEEDED
    assert stored_run.output_text == "done"


async def test_engine_stops_at_max_steps(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_running_run(uow_factory)
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id=f"call-{index}",
                        tool_name="echo",
                        input={"text": "again"},
                    )
                ]
            )
            for index in range(3)
        ]
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(
        uow_factory,
        provider,
        publisher,
        max_steps=2,
    )

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "failed"
    assert outcome.error_code is ErrorCode.HARNESS_STEP_LIMIT
    assert len(provider.requests) == 2

    async with uow_factory() as uow:
        stored_run = await uow.runs.get(run.id)

    assert stored_run.status is RunStatus.FAILED
    assert stored_run.error_code == ErrorCode.HARNESS_STEP_LIMIT.value


async def test_global_tool_timeout_caps_tool_definition_timeout(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_running_run(uow_factory)
    registry = ToolRegistry()
    registry.register(slow_tool())
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id="call-1",
                        tool_name="slow",
                        input={"text": "wait"},
                    )
                ]
            ),
            ModelResponse(text="recovered"),
        ]
    )
    engine = make_engine(
        uow_factory,
        provider,
        RecordingEventPublisher(),
        registry=registry,
        tool_timeout_seconds=0.01,
    )

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "completed"
    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run.id, "call-1")
    assert call.status is ToolCallStatus.FAILED
    assert call.error_code == ErrorCode.TOOL_EXECUTION_TIMEOUT.value


async def test_success_transition_cancel_conflict_returns_cancelled(
    uow_factory: UnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = await seed_running_run(uow_factory)
    provider = ScriptedModelProvider([ModelResponse(text="late success")])
    engine = make_engine(uow_factory, provider, RecordingEventPublisher())
    original_transition = RunRepository.transition

    async def reject_success(
        repository: RunRepository,
        run_id: str,
        target: RunStatus,
        **kwargs: object,
    ) -> Run:
        if target is RunStatus.SUCCEEDED:
            raise AgentKitError(
                ErrorCode.RUN_CANCELLED,
                "Run 已请求取消",
                http_status=409,
            )
        return await original_transition(repository, run_id, target, **kwargs)

    monkeypatch.setattr(RunRepository, "transition", reject_success)

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "cancelled"
    async with uow_factory() as uow:
        stored = await uow.runs.get(run.id)
    assert stored.status is RunStatus.CANCELLED


async def test_contract_failure_closes_remaining_tool_calls(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_running_run(uow_factory)
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id="call-1",
                        tool_name="echo",
                        input={},
                    ),
                    ToolCallDraft(
                        call_id="call-2",
                        tool_name="echo",
                        input={"text": "valid"},
                    ),
                ]
            )
        ]
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher)

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=asyncio.Event()))

    assert outcome.kind == "failed"
    assert outcome.error_code is ErrorCode.TOOL_INPUT_INVALID

    async with uow_factory() as uow:
        calls = await uow.tool_calls.list_for_run(run.id)
        messages = await uow.messages.list_for_session(run.session_id)
        stored_run = await uow.runs.get(run.id)

    assert [call.status for call in calls] == [
        ToolCallStatus.FAILED,
        ToolCallStatus.FAILED,
    ]
    assert [message.role for message in messages].count(MessageRole.TOOL) == 2
    assert stored_run.status is RunStatus.FAILED
    assert stored_run.error_code == ErrorCode.TOOL_INPUT_INVALID.value


async def test_preexisting_cancel_marks_run_cancelled(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_running_run(uow_factory)
    provider = ScriptedModelProvider([ModelResponse(text="never")])
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher)
    cancel = asyncio.Event()
    cancel.set()

    outcome = await engine.execute(EngineContext(run_id=run.id, cancel=cancel))

    assert outcome.kind == "cancelled"
    assert provider.requests == []

    async with uow_factory() as uow:
        stored_run = await uow.runs.get(run.id)

    assert stored_run.status is RunStatus.CANCELLED


async def test_cancel_during_text_stream_prevents_success(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_running_run(uow_factory)
    provider = ControlledModelProvider(ModelResponse(text="late response"))
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher)  # type: ignore[arg-type]
    cancel = asyncio.Event()
    task = asyncio.create_task(engine.execute(EngineContext(run_id=run.id, cancel=cancel)))

    await asyncio.wait_for(provider.started.wait(), timeout=1)
    async with uow_factory() as uow:
        await uow.runs.mark_cancel_requested(run.id)
        await uow.commit()
    cancel.set()
    provider.release.set()

    outcome = await asyncio.wait_for(task, timeout=1)

    assert outcome.kind == "cancelled"
    async with uow_factory() as uow:
        stored_run = await uow.runs.get(run.id)
        messages = await uow.messages.list_for_session(run.session_id)
    assert stored_run.status is RunStatus.CANCELLED
    assert [message.role for message in messages] == [MessageRole.USER]


async def test_cancel_during_remote_tool_stream_prevents_waiting(
    uow_factory: UnitOfWorkFactory,
) -> None:
    from prism_agent_kit.tools.testing import wait_for_host_tool

    run = await seed_running_run(uow_factory)
    registry = ToolRegistry()
    registry.register(wait_for_host_tool())
    provider = ControlledModelProvider(
        ModelResponse(
            tool_calls=[
                ToolCallDraft(
                    call_id="call-1",
                    tool_name="wait_for_host",
                    input={"value": "one"},
                )
            ]
        )
    )
    publisher = RecordingEventPublisher()
    engine = make_engine(
        uow_factory,
        provider,  # type: ignore[arg-type]
        publisher,
        registry=registry,
    )
    cancel = asyncio.Event()
    task = asyncio.create_task(engine.execute(EngineContext(run_id=run.id, cancel=cancel)))

    await asyncio.wait_for(provider.started.wait(), timeout=1)
    async with uow_factory() as uow:
        await uow.runs.mark_cancel_requested(run.id)
        await uow.commit()
    cancel.set()
    provider.release.set()

    outcome = await asyncio.wait_for(task, timeout=1)

    assert outcome.kind == "cancelled"
    async with uow_factory() as uow:
        stored_run = await uow.runs.get(run.id)
        calls = await uow.tool_calls.list_for_run(run.id)
        messages = await uow.messages.list_for_session(run.session_id)
    assert stored_run.status is RunStatus.CANCELLED
    assert calls == []
    assert [message.role for message in messages] == [MessageRole.USER]


async def test_cancel_takes_priority_over_model_error(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_running_run(uow_factory)
    provider = FailingControlledModelProvider(ModelResponse(text="unused"))
    publisher = RecordingEventPublisher()
    engine = make_engine(uow_factory, provider, publisher)  # type: ignore[arg-type]
    cancel = asyncio.Event()
    task = asyncio.create_task(engine.execute(EngineContext(run_id=run.id, cancel=cancel)))

    await asyncio.wait_for(provider.started.wait(), timeout=1)
    async with uow_factory() as uow:
        await uow.runs.mark_cancel_requested(run.id)
        await uow.commit()
    cancel.set()
    provider.release.set()

    outcome = await asyncio.wait_for(task, timeout=1)

    assert outcome.kind == "cancelled"
    async with uow_factory() as uow:
        stored_run = await uow.runs.get(run.id)
    assert stored_run.status is RunStatus.CANCELLED
