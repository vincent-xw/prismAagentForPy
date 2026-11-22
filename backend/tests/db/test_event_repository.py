from prism_agent_kit.core.models import Run, RunEvent
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_list_events_after_cursor(uow_factory: UnitOfWorkFactory) -> None:
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
        first = await uow.events.append(
            RunEvent(run_id=run.id, event_type="run.queued", payload={})
        )
        second = await uow.events.append(
            RunEvent(run_id=run.id, event_type="run.started", payload={})
        )
        await uow.commit()

    assert first.id is not None
    assert second.id is not None

    async with uow_factory() as uow:
        events = await uow.events.list_after(run.id, after_id=first.id)

    assert [event.id for event in events] == [second.id]
