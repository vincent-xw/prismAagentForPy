from pathlib import Path

import pytest
from tests.fakes import RecordingEventPublisher
from tests.support.skill_helpers import make_skill

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.application.skills.catalog import SkillCatalog
from prism_agent_kit.core.enums import MessageKind
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.prompts import PromptRegistry
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def make_services(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> tuple[RunService, SessionService, SkillCatalog]:
    make_skill(tmp_path, "pdf-tools", "Extract PDFs.", "# PDF tools")
    prompts = PromptRegistry()
    prompts.register(name="default", version="1", prompt="default system")
    catalog = SkillCatalog([tmp_path])
    runs = RunService(
        uow_factory=uow_factory,
        prompt_registry=prompts,
        model_name="test-model",
        default_prompt_ref="default@1",
        event_publisher=RecordingEventPublisher(),
        cancellation_registry=RunCancellationRegistry(),
        skill_catalog=catalog,
    )
    return runs, SessionService(uow_factory), catalog


async def test_skill_context_written_before_user_message(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    runs, sessions, _ = await make_services(uow_factory, tmp_path)
    session = await sessions.create(title="demo")

    run = await runs.create(session.id, input_text="hi", prompt_ref=None, skill_name="pdf-tools")

    async with uow_factory() as uow:
        messages = await uow.messages.list_for_session(session.id)

    assert [message.kind for message in messages] == [
        MessageKind.SKILL_CONTEXT,
        MessageKind.TEXT,
    ]
    assert run.skill_name == "pdf-tools"
    assert '<skill_content name="pdf-tools">' in str(messages[0].content)


async def test_unknown_skill_creates_nothing(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    runs, sessions, _ = await make_services(uow_factory, tmp_path)
    session = await sessions.create(title="demo")

    with pytest.raises(AgentKitError) as error:
        await runs.create(session.id, input_text="hi", prompt_ref=None, skill_name="nope")
    assert error.value.code is ErrorCode.SKILL_NOT_FOUND

    async with uow_factory() as uow:
        assert await uow.messages.list_for_session(session.id) == []


async def test_catalog_appended_to_system_prompt(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    runs, sessions, _ = await make_services(uow_factory, tmp_path)
    session = await sessions.create(title="demo")

    run = await runs.create(session.id, input_text="hi", prompt_ref=None)

    assert run.system_prompt.startswith("default system")
    assert "<available_skills>" in run.system_prompt
    assert "pdf-tools" in run.system_prompt


async def test_without_catalog_keeps_plain_prompt(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
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
    sessions = SessionService(uow_factory)
    session = await sessions.create(title="demo")

    run = await runs.create(session.id, input_text="hi", prompt_ref=None)

    assert run.system_prompt == "default system"
