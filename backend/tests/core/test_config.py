from pathlib import Path

from pydantic import SecretStr

from prism_agent_kit.core.config import Settings


def test_settings_parse_runtime_values(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "agent.db",
        api_token=SecretStr("test-token"),
        model_base_url="https://example.test/v1",
        model_api_key=SecretStr("secret"),
        model_name="deepseek-chat",
        model_token_encoding="cl100k_base",
    )

    assert settings.database_path == tmp_path / "agent.db"
    assert settings.model_name == "deepseek-chat"
    assert settings.api_token is not None
    assert settings.api_token.get_secret_value() == "test-token"


def test_empty_model_base_url_is_normalized_to_none(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "agent.db",
        model_base_url="",
    )

    assert settings.model_base_url is None


def test_empty_api_token_is_normalized_to_none(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "agent.db",
        api_token="",
    )

    assert settings.api_token is None


def test_workspace_defaults() -> None:
    settings = Settings()

    assert settings.workspace_index_max_file_bytes == 1_048_576
    assert settings.workspace_index_max_files == 20_000
    assert settings.workspace_tool_approval_timeout_seconds == 1_800
    assert settings.workspace_require_write_approval is True
