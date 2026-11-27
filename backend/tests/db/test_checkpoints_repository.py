from prism_agent_kit.core.models import CompactionCheckpoint
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_create_and_latest(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        first = await uow.checkpoints.create(
            CompactionCheckpoint(
                session_id=session.id,
                summary="first",
                first_kept_message_id=10,
                tokens_before=100,
                tokens_after=40,
                pruned_chars=20,
            )
        )
        await uow.commit()

    async with uow_factory() as uow:
        second = await uow.checkpoints.create(
            CompactionCheckpoint(
                session_id=session.id,
                summary="second",
                first_kept_message_id=20,
                tokens_before=120,
                tokens_after=50,
            )
        )
        await uow.commit()

    async with uow_factory() as uow:
        latest = await uow.checkpoints.latest(session.id)
        history = await uow.checkpoints.list_for_session(session.id)

    assert latest is not None and latest.id == second.id
    assert [item.summary for item in history] == ["first", "second"]
    assert first.session_id == session.id
