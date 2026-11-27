"""模型档案的校验、CRUD 与全局激活。"""

import re

from pydantic import BaseModel

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import ModelProfile
from prism_agent_kit.db.uow import UnitOfWorkFactory

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class ModelProfileInput(BaseModel):
    """新增/更新档案的入参。"""

    name: str
    base_url: str
    model: str
    api_key_env: str
    context_window: int
    max_output_tokens: int


class ModelProfileService:
    """档案的全局唯一 active 与 CRUD。"""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def list(self) -> list[ModelProfile]:
        async with self._uow_factory() as uow:
            return await uow.model_profiles.list_all()

    async def get(self, profile_id: str) -> ModelProfile:
        async with self._uow_factory() as uow:
            return await uow.model_profiles.get(profile_id)

    async def active(self) -> ModelProfile | None:
        async with self._uow_factory() as uow:
            return await uow.model_profiles.active()

    async def create(self, payload: ModelProfileInput) -> ModelProfile:
        self._validate(payload)
        async with self._uow_factory() as uow:
            await self._ensure_name_free(uow, payload.name, exclude_id=None)
            profile = await uow.model_profiles.create(
                ModelProfile(
                    name=payload.name,
                    base_url=payload.base_url,
                    model=payload.model,
                    api_key_env=payload.api_key_env,
                    context_window=payload.context_window,
                    max_output_tokens=payload.max_output_tokens,
                )
            )
            await uow.commit()
        return profile

    async def update(self, profile_id: str, payload: ModelProfileInput) -> ModelProfile:
        self._validate(payload)
        async with self._uow_factory() as uow:
            await self._ensure_name_free(uow, payload.name, exclude_id=profile_id)
            updated = await uow.model_profiles.update(
                profile_id,
                name=payload.name,
                base_url=payload.base_url,
                model=payload.model,
                api_key_env=payload.api_key_env,
                context_window=payload.context_window,
                max_output_tokens=payload.max_output_tokens,
            )
            await uow.commit()
            return updated

    async def delete(self, profile_id: str) -> None:
        async with self._uow_factory() as uow:
            profile = await uow.model_profiles.get(profile_id)
            if profile.is_active:
                raise AgentKitError(
                    ErrorCode.MODEL_PROFILE_IN_USE,
                    "不能删除当前激活的模型档案，请先切换到其他档案",
                    http_status=409,
                    details={"profile_id": profile_id},
                )
            await uow.model_profiles.delete(profile_id)
            await uow.commit()

    async def activate(self, profile_id: str) -> ModelProfile:
        async with self._uow_factory() as uow:
            profile = await uow.model_profiles.set_active(profile_id)
            await uow.commit()
            return profile

    @staticmethod
    def _validate(payload: ModelProfileInput) -> None:
        if not payload.name.strip() or len(payload.name) > 128:
            raise _invalid("档案名不能为空且不超过 128 字符")
        if not payload.base_url.startswith(("http://", "https://")):
            raise _invalid("base_url 必须是 http(s) 地址")
        if not payload.model.strip():
            raise _invalid("model 不能为空")
        if _ENV_NAME.fullmatch(payload.api_key_env) is None:
            raise _invalid("api_key_env 必须是环境变量名，例如 OPENAI_API_KEY")
        if payload.context_window <= 0 or payload.max_output_tokens <= 0:
            raise _invalid("context_window 与 max_output_tokens 必须为正数")
        if payload.max_output_tokens >= payload.context_window:
            raise _invalid("max_output_tokens 必须小于 context_window")

    @staticmethod
    async def _ensure_name_free(uow: object, name: str, *, exclude_id: str | None) -> None:
        profiles = await uow.model_profiles.list_all()  # type: ignore[attr-defined]
        if any(item.name == name and item.id != exclude_id for item in profiles):
            raise _invalid("档案名已存在")


def _invalid(message: str) -> AgentKitError:
    return AgentKitError(ErrorCode.MODEL_PROFILE_INVALID, message, http_status=422)
