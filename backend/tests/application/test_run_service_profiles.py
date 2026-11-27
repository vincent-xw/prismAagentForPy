from tests.fakes import RecordingEventPublisher

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.model_profile_service import (
    ModelProfileInput,
    ModelProfileService,
)
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.core.prompts import PromptRegistry
from prism_agent_kit.db.uow import UnitOfWorkFactory


def make_run_service(uow_factory: UnitOfWorkFactory, profiles: ModelProfileService) -> RunService:
    prompts = PromptRegistry()
    prompts.register(name="default", version="1", prompt="default system")
    return RunService(
        uow_factory=uow_factory,
        prompt_registry=prompts,
        model_name="env-model",
        default_prompt_ref="default@1",
        event_publisher=RecordingEventPublisher(),
        cancellation_registry=RunCancellationRegistry(),
        profiles=profiles,
    )


async def test_run_snapshots_active_profile(uow_factory: UnitOfWorkFactory) -> None:
    profiles = ModelProfileService(uow_factory)
    profile = await profiles.create(
        ModelProfileInput(
            name="p1",
            base_url="https://api.example.com/v1",
            model="m1",
            api_key_env="OPENAI_API_KEY",
            context_window=64_000,
            max_output_tokens=4_096,
        )
    )
    await profiles.activate(profile.id)
    service = make_run_service(uow_factory, profiles)
    session = await SessionService(uow_factory).create(title="demo")

    run = await service.create(session.id, input_text="hi", prompt_ref=None)

    assert run.model == "m1"
    assert run.model_profile_id == profile.id
    assert run.model_context_window == 64_000
    assert run.model_max_output_tokens == 4_096


async def test_run_falls_back_to_env_when_no_profile(
    uow_factory: UnitOfWorkFactory,
) -> None:
    service = make_run_service(uow_factory, ModelProfileService(uow_factory))
    session = await SessionService(uow_factory).create(title="demo")

    run = await service.create(session.id, input_text="hi", prompt_ref=None)

    assert run.model == "env-model"
    assert run.model_profile_id is None
