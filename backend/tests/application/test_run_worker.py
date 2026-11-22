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
