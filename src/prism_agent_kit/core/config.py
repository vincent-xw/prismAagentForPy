import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/prism_agent_kit"
    cors_origins: list[str] = Field(default_factory=list)

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
