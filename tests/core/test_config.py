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
