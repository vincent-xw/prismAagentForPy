import pytest

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_create_and_load_session(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        created = await uow.sessions.create(title="demo")
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.sessions.get(created.id)

    assert loaded == created


async def test_list_sessions_returns_newest_first(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        first = await uow.sessions.create(title="first")
        second = await uow.sessions.create(title="second")
        await uow.commit()

    async with uow_factory() as uow:
        sessions = await uow.sessions.list()

    assert [session.id for session in sessions] == [second.id, first.id]


async def test_missing_session_raises_not_found(
    uow_factory: UnitOfWorkFactory,
) -> None:
    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.sessions.get("missing")

    assert error.value.code is ErrorCode.SESSION_NOT_FOUND
    assert error.value.http_status == 404
