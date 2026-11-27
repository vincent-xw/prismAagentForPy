"""按模型档案构造 Provider，并按档案版本缓存。"""

import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from pydantic import SecretStr

from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import ModelProfile, Run
from prism_agent_kit.core.ports import ModelProvider
from prism_agent_kit.providers.openai_compatible import OpenAICompatibleProvider

ProviderResolver = Callable[[Run], Awaitable[ModelProvider]]


def has_credential(profile: ModelProfile) -> bool:
    """库内密钥或对应环境变量任一存在即视为可用。"""
    return bool(profile.api_key) or bool(os.environ.get(profile.api_key_env))


class ProviderFactory:
    """构造并缓存档案 Provider；同一档案内容更新后重建。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, tuple[datetime, OpenAICompatibleProvider]] = {}

    def build(self, profile: ModelProfile) -> OpenAICompatibleProvider:
        cached = self._cache.get(profile.id)
        if cached is not None and cached[0] == profile.updated_at:
            return cached[1]
        api_key = profile.api_key or os.environ.get(profile.api_key_env)
        if not api_key:
            raise AgentKitError(
                ErrorCode.MODEL_PROFILE_INVALID,
                f"环境变量 {profile.api_key_env} 未设置",
                http_status=422,
                details={"profile_id": profile.id},
            )
        provider = OpenAICompatibleProvider(
            model_name=profile.model,
            base_url=profile.base_url,
            api_key=SecretStr(api_key),
            timeout_seconds=self._settings.model_timeout_seconds,
        )
        self._cache[profile.id] = (profile.updated_at, provider)
        return provider

    def build_default(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider.from_settings(self._settings)

    async def aclose(self) -> None:
        providers: list[Any] = [provider for _, provider in self._cache.values()]
        self._cache.clear()
        for provider in providers:
            await provider.aclose()
