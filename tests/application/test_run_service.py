from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.core.enums import EventType, MessageRole
from prism_agent_kit.core.prompts import PromptRegistry
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_create_run_writes_user_message_prompt_snapshot_and_event(
    uow_factory: UnitOfWorkFactory,
) -> None:
    prompts = PromptRegistry()
    prompts.register(name="default", version="1", prompt="default system")
    sessions = SessionService(uow_factory)
    runs = RunService(
        uow_factory=uow_factory,
        prompt_registry=prompts,
        model_name="test-model",
        default_prompt_ref="default@1",
    )
    session = await sessions.create(title="demo")

    run = await runs.create(
        session.id,
        input_text="hello",
        prompt_ref=None,
        metadata={"client": "test"},
    )

    assert run.prompt_ref == "default@1"
    assert run.system_prompt == "default system"
    assert run.model == "test-model"

    async with uow_factory() as uow:
        messages = await uow.messages.list_for_session(session.id)
        events = await uow.events.list_after(run.id)

    assert len(messages) == 1
    assert messages[0].role is MessageRole.USER
    assert messages[0].content == "hello"
    assert [event.event_type for event in events] == [EventType.RUN_QUEUED]
    assert events[0].payload == {
        "prompt_ref": "default@1",
        "metadata": {"client": "test"},
    }
