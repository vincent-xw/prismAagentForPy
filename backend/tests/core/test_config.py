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


def test_mcp_defaults() -> None:
    settings = Settings()

    assert settings.mcp_connect_timeout_seconds == 10.0
    assert settings.mcp_tool_timeout_seconds == 30.0
    assert settings.mcp_max_result_bytes == 204_800


def test_skills_defaults() -> None:
    settings = Settings()

    assert settings.skills_catalog_max_chars == 8000
    assert settings.skills_max_tool_result_chars == 60_000
    assert settings.skills_paths == ""


def test_compaction_defaults() -> None:
    settings = Settings()

    assert settings.compaction_threshold_ratio == 0.85
    assert settings.compaction_retain_ratio == 0.2
    assert settings.compaction_retain_tokens == 20_000
    assert settings.compaction_prune_threshold_chars == 8_000
    assert settings.compaction_prune_head_chars == 2_000
    assert settings.compaction_prune_tail_chars == 2_000
    assert settings.compaction_timeout_seconds == 30.0
