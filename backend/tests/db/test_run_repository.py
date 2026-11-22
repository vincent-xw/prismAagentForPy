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


async def test_cancel_request_does_not_modify_terminal_run(
    uow_factory: UnitOfWorkFactory,
) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        run = await uow.runs.create(make_run(session.id))
        await uow.commit()

    async with uow_factory() as uow:
        await uow.runs.claim_next()
        await uow.runs.transition(run.id, RunStatus.SUCCEEDED)
        await uow.commit()

    async with uow_factory() as uow:
        unchanged = await uow.runs.mark_cancel_requested(run.id)
        await uow.commit()

    assert unchanged.status is RunStatus.SUCCEEDED
    assert unchanged.cancel_requested_at is None


async def test_stale_transition_cannot_overwrite_concurrent_terminal_state(
    uow_factory: UnitOfWorkFactory,
) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        run = await uow.runs.create(make_run(session.id))
        await uow.commit()

    async with uow_factory() as uow:
        await uow.runs.claim_next()
        await uow.commit()

    async with uow_factory() as stale_uow, uow_factory() as concurrent_uow:
        await stale_uow.runs.get(run.id)
        await concurrent_uow.runs.transition(run.id, RunStatus.CANCELLED)
        await concurrent_uow.commit()

        with pytest.raises(AgentKitError) as error:
            await stale_uow.runs.transition(run.id, RunStatus.SUCCEEDED)

    assert error.value.code is ErrorCode.INVALID_RUN_TRANSITION
    async with uow_factory() as uow:
        stored = await uow.runs.get(run.id)
    assert stored.status is RunStatus.CANCELLED


async def test_success_transition_rejects_committed_cancel_request(
    uow_factory: UnitOfWorkFactory,
) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        run = await uow.runs.create(make_run(session.id))
        await uow.commit()

    async with uow_factory() as uow:
        await uow.runs.claim_next()
        await uow.commit()

    async with uow_factory() as uow:
        await uow.runs.mark_cancel_requested(run.id)
        await uow.commit()

    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.runs.transition(
                run.id,
                RunStatus.SUCCEEDED,
                require_no_cancel_request=True,
            )

    assert error.value.code is ErrorCode.RUN_CANCELLED
    async with uow_factory() as uow:
        stored = await uow.runs.get(run.id)
    assert stored.status is RunStatus.RUNNING
    assert stored.cancel_requested_at is not None
