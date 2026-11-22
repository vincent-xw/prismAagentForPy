from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.models import Message, Run
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_append_and_list_messages_in_order(
    uow_factory: UnitOfWorkFactory,
) -> None:
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
        first = await uow.messages.append(
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.USER,
                content="hello",
            )
        )
        second = await uow.messages.append(
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.ASSISTANT,
                content="world",
            )
        )
        await uow.commit()

    assert first.id is not None
    assert second.id is not None
    assert second.id > first.id

    async with uow_factory() as uow:
        messages = await uow.messages.list_for_session(session.id)

    assert [message.id for message in messages] == [first.id, second.id]
