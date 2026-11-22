import pytest

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.prompts import PromptRegistry


def test_prompt_ref_requires_explicit_version() -> None:
    registry = PromptRegistry()
    registry.register(name="default", version="1", prompt="system")

    with pytest.raises(AgentKitError) as error:
        registry.get_by_ref("default")

    assert error.value.code is ErrorCode.INVALID_PROMPT_REF
    assert error.value.http_status == 400


def test_get_prompt_by_explicit_ref() -> None:
    registry = PromptRegistry()
    registered = registry.register(name="default", version="1", prompt="system")

    loaded = registry.get_by_ref("default@1")

    assert loaded == registered
    assert loaded.content == "system"


def test_duplicate_prompt_version_is_rejected() -> None:
    registry = PromptRegistry()
    registry.register(name="default", version="1", prompt="first")

    with pytest.raises(AgentKitError) as error:
        registry.register(name="default", version="1", prompt="second")

    assert error.value.code is ErrorCode.INVALID_PROMPT_REF


def test_missing_prompt_version_is_not_found() -> None:
    registry = PromptRegistry()

    with pytest.raises(AgentKitError) as error:
        registry.get(name="default", version="9")

    assert error.value.code is ErrorCode.PROMPT_NOT_FOUND
    assert error.value.http_status == 404
