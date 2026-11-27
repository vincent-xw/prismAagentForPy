import pytest

from prism_agent_kit.application.model_profile_service import (
    ModelProfileInput,
    ModelProfileService,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.db.uow import UnitOfWorkFactory


def profile_input(**overrides: object) -> ModelProfileInput:
    values: dict[str, object] = {
        "name": "primary",
        "base_url": "https://api.example.com/v1",
        "model": "model-a",
        "api_key_env": "OPENAI_API_KEY",
        "context_window": 128_000,
        "max_output_tokens": 8_192,
    }
    values.update(overrides)
    return ModelProfileInput(**values)


async def test_activate_is_exclusive(uow_factory: UnitOfWorkFactory) -> None:
    service = ModelProfileService(uow_factory)
    first = await service.create(profile_input(name="a"))
    second = await service.create(profile_input(name="b"))

    await service.activate(first.id)
    await service.activate(second.id)

    assert (await service.active()).id == second.id  # type: ignore[union-attr]
    rows = await service.list()
    assert sum(1 for row in rows if row.is_active) == 1


async def test_delete_active_rejected(uow_factory: UnitOfWorkFactory) -> None:
    service = ModelProfileService(uow_factory)
    profile = await service.create(profile_input())
    await service.activate(profile.id)

    with pytest.raises(AgentKitError) as error:
        await service.delete(profile.id)
    assert error.value.code is ErrorCode.MODEL_PROFILE_IN_USE


async def test_duplicate_name_rejected(uow_factory: UnitOfWorkFactory) -> None:
    service = ModelProfileService(uow_factory)
    await service.create(profile_input())
    with pytest.raises(AgentKitError) as error:
        await service.create(profile_input())
    assert error.value.code is ErrorCode.MODEL_PROFILE_INVALID


async def test_invalid_fields_rejected(uow_factory: UnitOfWorkFactory) -> None:
    service = ModelProfileService(uow_factory)
    for payload in [
        profile_input(base_url="ftp://x"),
        profile_input(api_key_env="not-an-env"),
        profile_input(context_window=100, max_output_tokens=100),
    ]:
        with pytest.raises(AgentKitError) as error:
            await service.create(payload)
        assert error.value.code is ErrorCode.MODEL_PROFILE_INVALID


async def test_update_and_get(uow_factory: UnitOfWorkFactory) -> None:
    service = ModelProfileService(uow_factory)
    profile = await service.create(profile_input())

    updated = await service.update(profile.id, profile_input(name="renamed", model="model-b"))

    assert updated.name == "renamed" and updated.model == "model-b"
    assert (await service.get(profile.id)).name == "renamed"
