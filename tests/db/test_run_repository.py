import pytest

from prism_agent_kit.core.enums import RunStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Run
from prism_agent_kit.db.uow import UnitOfWorkFactory


def make_run(session_id: str, input_text: str = "hello") -> Run:
    """构造测试用 Run 领域对象。"""
    return Run(
        session_id=session_id,
        input_text=input_text,
        prompt_name="default",
        prompt_version="1",
        system_prompt="system",
        model="test-model",
    )


async def test_create_and_load_run(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create(title="demo")
        created = await uow.runs.create(make_run(session.id))
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.runs.get(created.id)
        active = await uow.runs.get_active(session.id)

    assert loaded == created
    assert active == created


async def test_claim_next_only_claims_queued_run(
    uow_factory: UnitOfWorkFactory,
) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        created = await uow.runs.create(make_run(session.id))
        await uow.commit()

    async with uow_factory() as uow:
        claimed = await uow.runs.claim_next()
        await uow.commit()

    assert claimed is not None
    assert claimed.id == created.id
    assert claimed.status is RunStatus.RUNNING
    assert claimed.started_at is not None

    async with uow_factory() as uow:
        second_claim = await uow.runs.claim_next()

    assert second_claim is None


async def test_transition_rejects_terminal_run(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        run = await uow.runs.create(make_run(session.id))
        await uow.commit()

    async with uow_factory() as uow:
        await uow.runs.claim_next()
        finished = await uow.runs.transition(run.id, RunStatus.SUCCEEDED)
        await uow.commit()

    assert finished.status is RunStatus.SUCCEEDED
    assert finished.finished_at is not None

    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.runs.transition(run.id, RunStatus.QUEUED)

    assert error.value.code is ErrorCode.INVALID_RUN_TRANSITION


async def test_second_active_run_is_rejected(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        await uow.runs.create(make_run(session.id, "first"))
        await uow.commit()

    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.runs.create(make_run(session.id, "second"))

    assert error.value.code is ErrorCode.RUN_CONFLICT
    assert error.value.http_status == 409
