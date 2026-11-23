from datetime import timedelta

from tests.fakes import RecordingEventPublisher

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.run_worker import RunWorker
from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.engine import EngineOutcome
from prism_agent_kit.core.enums import (
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import ErrorCode
from prism_agent_kit.core.models import Message, Run, ToolCall, utc_now
from prism_agent_kit.db.uow import UnitOfWorkFactory


class NoopEngine:
    async def execute(self, context: object) -> EngineOutcome:
        return EngineOutcome(kind="completed")

    async def resume(self, context: object) -> EngineOutcome:
        return EngineOutcome(kind="completed")

    async def cancel(self, run_id: str) -> EngineOutcome:
        return EngineOutcome(kind="cancelled")


def make_worker(uow_factory: UnitOfWorkFactory) -> RunWorker:
    return RunWorker(
        uow_factory=uow_factory,
        engine=NoopEngine(),  # type: ignore[arg-type]
        event_publisher=RecordingEventPublisher(),
        cancellation_registry=RunCancellationRegistry(),
    )


async def seed_running_with_open_tool(
    uow_factory: UnitOfWorkFactory,
) -> tuple[Run, str]:
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
        assert claimed is not None
        assistant = await uow.messages.append(
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.ASSISTANT,
                content="",
            )
        )
        assert assistant.id is not None
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-1",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="wait_for_host",
                    execution_mode=ExecutionMode.REMOTE,
                    input={},
                    input_digest=canonical_json_digest({}),
                )
            ]
        )
        await uow.commit()
    return run, session.id


async def seed_waiting_with_expired_tool(
    uow_factory: UnitOfWorkFactory,
) -> tuple[Run, str]:
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
        assert claimed is not None
        assistant = await uow.messages.append(
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.ASSISTANT,
                content="",
            )
        )
        assert assistant.id is not None
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-1",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="wait_for_host",
                    execution_mode=ExecutionMode.REMOTE,
                    input={},
                    input_digest=canonical_json_digest({}),
                    expires_at=utc_now() - timedelta(minutes=1),
                )
            ]
        )
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_TOOL)
        await uow.commit()
    return run, session.id


async def test_startup_marks_running_run_interrupted_and_closes_tools(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run, session_id = await seed_running_with_open_tool(uow_factory)
    worker = make_worker(uow_factory)

    recovered = await worker.recover_interrupted_runs()

    assert recovered == 1
    async with uow_factory() as uow:
        stored_run = await uow.runs.get(run.id)
        calls = await uow.tool_calls.list_for_run(run.id)
        messages = await uow.messages.list_for_session(session_id)
        events = await uow.events.list_after(run.id)

    assert stored_run.status is RunStatus.FAILED
    assert stored_run.error_code == ErrorCode.PROCESS_INTERRUPTED.value
    assert all(call.status is ToolCallStatus.FAILED for call in calls)
    assert [message.role for message in messages].count(MessageRole.TOOL) == 1
    assert any(event.event_type.value == "run.failed" for event in events)


async def test_expired_remote_tool_requeues_run(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run, _ = await seed_waiting_with_expired_tool(uow_factory)
    worker = make_worker(uow_factory)

    expired_count = await worker.sweep_expired_tool_calls(now=utc_now())

    assert expired_count == 1
    async with uow_factory() as uow:
        stored_run = await uow.runs.get(run.id)
        call = await uow.tool_calls.get(run.id, "call-1")
        events = await uow.events.list_after(run.id)

    assert call.status is ToolCallStatus.EXPIRED
    assert call.error_code == ErrorCode.REMOTE_TOOL_TIMEOUT.value
    assert stored_run.status is RunStatus.QUEUED
    event_types = {event.event_type.value for event in events}
    assert "tool.expired" in event_types
    assert "run.requeued" in event_types


async def seed_waiting_for_approval_run(uow_factory: UnitOfWorkFactory) -> tuple[str, str]:
    """创建 waiting_for_approval Run 与待审批调用。"""
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
            Message(session_id=session.id, run_id=run.id, role=MessageRole.USER, content="hello")
        )
        await uow.commit()
    async with uow_factory() as uow:
        await uow.runs.claim_next()
        assistant = await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.ASSISTANT, content="")
        )
        assert assistant.id is not None
        payload = {"path": "a.md", "content": "hi", "mode": "overwrite"}
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-approve",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="file_write",
                    execution_mode=ExecutionMode.LOCAL,
                    input=payload,
                    input_digest=canonical_json_digest(payload),
                )
            ]
        )
        await uow.tool_calls.await_call(run.id, "call-approve", utc_now() + timedelta(seconds=600))
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_APPROVAL)
        await uow.commit()
        return run.id, "call-approve"


async def test_recovery_keeps_waiting_for_approval(uow_factory: UnitOfWorkFactory) -> None:
    run_id, call_id = await seed_waiting_for_approval_run(uow_factory)
    worker = make_worker(uow_factory)

    assert await worker.recover_interrupted_runs() == 0
    async with uow_factory() as uow:
        run = await uow.runs.get(run_id)
        assert run.status is RunStatus.WAITING_FOR_APPROVAL
        call = await uow.tool_calls.get(run_id, call_id)
        assert call.status is ToolCallStatus.AWAITING_APPROVAL
