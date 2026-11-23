from tests.fakes import RecordingEventPublisher

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.run_worker import RunWorker
from prism_agent_kit.core.engine import EngineContext, EngineOutcome
from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.models import Message, Run
from prism_agent_kit.db.uow import UnitOfWorkFactory


class RecordingEngine:
    """记录 Worker 选择 execute 还是 resume。"""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.resumed: list[str] = []

    async def execute(self, context: EngineContext) -> EngineOutcome:
        self.executed.append(context.run_id)
        return EngineOutcome(kind="completed")

    async def resume(self, context: EngineContext) -> EngineOutcome:
        self.resumed.append(context.run_id)
        return EngineOutcome(kind="completed")

    async def cancel(self, run_id: str) -> EngineOutcome:
        return EngineOutcome(kind="cancelled")


def make_worker(
    uow_factory: UnitOfWorkFactory,
    engine: RecordingEngine,
) -> tuple[RunWorker, RecordingEventPublisher, RunCancellationRegistry]:
    publisher = RecordingEventPublisher()
    registry = RunCancellationRegistry()
    worker = RunWorker(
        uow_factory=uow_factory,
        engine=engine,
        event_publisher=publisher,
        cancellation_registry=registry,
        concurrency=2,
        poll_interval_seconds=0.01,
        sweep_interval_seconds=0.05,
    )
    return worker, publisher, registry


async def seed_queued_run(
    uow_factory: UnitOfWorkFactory,
    *,
    step_count: int = 0,
) -> Run:
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
        if step_count:
            await uow.runs.update_step_count(run.id, step_count)
        await uow.commit()
    return run


async def test_worker_claims_queued_run_and_invokes_engine(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_queued_run(uow_factory)
    engine = RecordingEngine()
    worker, _, _ = make_worker(uow_factory, engine)

    outcome = await worker.run_once()

    assert outcome is not None
    assert outcome.kind == "completed"
    assert engine.executed == [run.id]


async def test_worker_uses_resume_after_persisted_step(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run = await seed_queued_run(uow_factory, step_count=1)
    engine = RecordingEngine()
    worker, _, _ = make_worker(uow_factory, engine)

    await worker.run_once()

    assert engine.executed == []
    assert engine.resumed == [run.id]


async def test_cancellation_registry_sets_registered_run() -> None:
    registry = RunCancellationRegistry()
    cancel = registry.register("run-1")

    assert registry.cancel("missing") is False
    assert registry.cancel("run-1") is True
    assert cancel.is_set()

    registry.unregister("run-1")
    assert registry.cancel("run-1") is False


async def test_start_and_stop_worker_without_runs(
    uow_factory: UnitOfWorkFactory,
) -> None:
    worker, _, _ = make_worker(uow_factory, RecordingEngine())

    await worker.start()
    await worker.stop()


async def seed_awaiting_approval_run(
    uow_factory: UnitOfWorkFactory,
    *,
    expires_in: int,
) -> tuple[str, str]:
    """创建 waiting_for_approval Run 与一个待审批调用。"""
    from datetime import timedelta

    from prism_agent_kit.core.digests import canonical_json_digest
    from prism_agent_kit.core.enums import ExecutionMode, RunStatus
    from prism_agent_kit.core.models import ToolCall, utc_now

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
        await uow.tool_calls.await_call(
            run.id, "call-approve", utc_now() + timedelta(seconds=expires_in)
        )
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_APPROVAL)
        await uow.commit()
        return run.id, "call-approve"


async def test_sweep_expires_awaiting_approval(uow_factory: UnitOfWorkFactory) -> None:
    from prism_agent_kit.core.enums import RunStatus, ToolCallStatus
    from prism_agent_kit.core.errors import ErrorCode

    run_id, call_id = await seed_awaiting_approval_run(uow_factory, expires_in=-5)
    worker, _, _ = make_worker(uow_factory, RecordingEngine())

    count = await worker.sweep_expired_tool_calls()

    assert count == 1
    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run_id, call_id)
        assert call.status is ToolCallStatus.EXPIRED
        assert call.error_code == ErrorCode.TOOL_APPROVAL_TIMEOUT.value
        run = await uow.runs.get(run_id)
        assert run.status is RunStatus.QUEUED


async def test_sweep_expired_approval_with_pending_remote_moves_to_waiting_for_tool(
    uow_factory: UnitOfWorkFactory,
) -> None:
    """审批超时但同轮远端仍 pending 时, Run 必须转 waiting_for_tool 而不是卡住。"""
    from datetime import timedelta

    from prism_agent_kit.core.digests import canonical_json_digest
    from prism_agent_kit.core.enums import ExecutionMode, RunStatus, ToolCallStatus
    from prism_agent_kit.core.models import ToolCall, utc_now

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
        write_payload = {"path": "a.md", "content": "hi", "mode": "overwrite"}
        remote_payload = {"value": "one"}
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-approve",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="file_write",
                    execution_mode=ExecutionMode.LOCAL,
                    input=write_payload,
                    input_digest=canonical_json_digest(write_payload),
                ),
                ToolCall(
                    id="call-remote",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="wait_for_host",
                    execution_mode=ExecutionMode.REMOTE,
                    input=remote_payload,
                    input_digest=canonical_json_digest(remote_payload),
                    expires_at=utc_now() + timedelta(minutes=5),
                ),
            ]
        )
        await uow.tool_calls.await_call(run.id, "call-approve", utc_now() - timedelta(seconds=5))
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_APPROVAL)
        await uow.commit()
        run_id = run.id

    worker, _, _ = make_worker(uow_factory, RecordingEngine())
    await worker.sweep_expired_tool_calls()

    async with uow_factory() as uow:
        refreshed = await uow.runs.get(run_id)
        assert refreshed.status is RunStatus.WAITING_FOR_TOOL
        remote = await uow.tool_calls.get(run_id, "call-remote")
        assert remote.status is ToolCallStatus.PENDING
