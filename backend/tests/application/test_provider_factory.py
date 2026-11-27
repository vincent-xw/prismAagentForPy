from datetime import UTC, datetime

import pytest

from prism_agent_kit.application.provider_factory import ProviderFactory
from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import ModelProfile


def make_profile(**overrides: object) -> ModelProfile:
    values: dict[str, object] = {
        "name": "p1",
        "base_url": "https://api.example.com/v1",
        "model": "model-a",
        "api_key_env": "TEST_PROFILE_KEY",
        "context_window": 64_000,
        "max_output_tokens": 4_096,
    }
    values.update(overrides)
    return ModelProfile(**values)  # type: ignore[arg-type]


def test_builds_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROFILE_KEY", "sk-test")
    factory = ProviderFactory(Settings())
    profile = make_profile()

    first = factory.build(profile)
    second = factory.build(profile)

    assert first is second


def test_rebuilds_after_update(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PROFILE_KEY", "sk-test")
    factory = ProviderFactory(Settings())
    profile = make_profile()
    first = factory.build(profile)

    updated = profile.model_copy(update={"updated_at": datetime(2026, 1, 2, tzinfo=UTC)})
    assert factory.build(updated) is not first


def test_missing_key_rejected() -> None:
    factory = ProviderFactory(Settings())
    with pytest.raises(AgentKitError) as error:
        factory.build(make_profile(api_key_env="MISSING_KEY_FOR_TEST"))
    assert error.value.code is ErrorCode.MODEL_PROFILE_INVALID
