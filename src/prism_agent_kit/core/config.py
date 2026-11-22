import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from platformdirs import user_data_dir
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置统一从环境变量或 .env 文件读取。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PRISM_AGENT_KIT_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PrismAgentKit API"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)

    database_path: Path | None = None
    api_token: SecretStr | None = None
    default_prompt_ref: str = "default@1"
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    model_name: str | None = None
    model_context_window: int | None = None
    model_max_output_tokens: int | None = None
    model_token_encoding: str | None = None
    model_timeout_seconds: float = 30.0
    context_safety_margin_tokens: int = 2048
    max_steps: int = 10
    tool_timeout_seconds: float = 30.0
    remote_tool_timeout_seconds: float = 300.0
    worker_concurrency: int = 2
    sse_heartbeat_seconds: float = 15.0

    @property
    def resolved_database_path(self) -> Path:
        """返回实际使用的 SQLite 文件路径。未配置时落到平台数据目录。"""
        if self.database_path is not None:
            return self.database_path.expanduser()
        return Path(user_data_dir("prism-agent-kit")) / "agent.db"

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        """保证 API 前缀以斜杠开头且不以斜杠结尾。"""
        normalized = f"/{value.strip('/')}" if value.strip("/") else ""
        if not normalized:
            raise ValueError("api_prefix 不能为空")
        return normalized

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """校验并规范化日志级别。"""
        normalized = value.upper()
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(f"无效日志级别: {value}")
        return normalized


@lru_cache
def get_settings() -> Settings:
    """返回进程级复用的配置实例。"""
    return Settings()
