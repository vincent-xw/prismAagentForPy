from datetime import UTC, datetime

from tests.fakes import RecordingEventPublisher

from prism_agent_kit.application.cancellation import RunCancellationRegistry
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
        event_publisher=RecordingEventPublisher(),
        cancellation_registry=RunCancellationRegistry(),
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


async def test_create_run_touches_session_activity(
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
        event_publisher=RecordingEventPublisher(),
        cancellation_registry=RunCancellationRegistry(),
    )
    session = await sessions.create(title="demo")
    old_activity = datetime(2000, 1, 1, tzinfo=UTC)
    async with uow_factory() as uow:
        await uow.sessions.touch(session.id, at=old_activity)
        await uow.commit()

    await runs.create(
        session.id,
        input_text="hello",
        prompt_ref=None,
    )

    updated = await sessions.get(session.id)
    assert updated.updated_at > old_activity


class _ActiveWorkspace:
    """返回固定活跃工作区的测试替身。"""

    def __init__(self, workspace: object) -> None:
        self._workspace = workspace

    async def active(self) -> object:
        return self._workspace


async def test_session_binds_active_workspace(uow_factory: UnitOfWorkFactory) -> None:
    from prism_agent_kit.core.workspace import Workspace

    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path="/tmp/project-a"))
        await uow.commit()
    sessions = SessionService(uow_factory, workspace_service=_ActiveWorkspace(workspace))

    session = await sessions.create(title="demo")

    assert session.workspace_id == workspace.id


async def test_run_inherits_session_workspace_even_after_switch(
    uow_factory: UnitOfWorkFactory,
) -> None:
    from prism_agent_kit.core.workspace import Workspace

    async with uow_factory() as uow:
        first = await uow.workspaces.create(Workspace(root_path="/tmp/project-a"))
        second = await uow.workspaces.create(Workspace(root_path="/tmp/project-b"))
        await uow.commit()
    sessions = SessionService(uow_factory, workspace_service=_ActiveWorkspace(first))
    session = await sessions.create(title="demo")
    prompts = PromptRegistry()
    prompts.register(name="default", version="1", prompt="default system")
    runs = RunService(
        uow_factory=uow_factory,
        prompt_registry=prompts,
        model_name="test-model",
        default_prompt_ref="default@1",
        event_publisher=RecordingEventPublisher(),
        cancellation_registry=RunCancellationRegistry(),
    )
    # 激活工作区已切到 second，但会话仍绑定 first
    sessions_now = SessionService(uow_factory, workspace_service=_ActiveWorkspace(second))
    assert (await sessions_now.get(session.id)).workspace_id == first.id

    run = await runs.create(session.id, input_text="hello", prompt_ref=None, metadata=None)

    assert run.workspace_id == first.id


async def test_run_without_session_workspace_stays_unbound(
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
        event_publisher=RecordingEventPublisher(),
        cancellation_registry=RunCancellationRegistry(),
    )
    session = await sessions.create(title="demo")

    run = await runs.create(session.id, input_text="hello", prompt_ref=None, metadata=None)

    assert run.workspace_id is None
