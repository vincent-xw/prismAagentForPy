"""模型档案管理接口。"""

import time

from fastapi import APIRouter, status

from prism_agent_kit.api.dependencies import (
    ModelProfileServiceDependency,
    ProviderFactoryDependency,
)
from prism_agent_kit.api.schemas import (
    ModelProfileCreate,
    ModelProfileProbeView,
    ModelProfileView,
)
from prism_agent_kit.application.model_profile_service import ModelProfileInput
from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.errors import AgentKitError
from prism_agent_kit.core.models import Message, ModelProfile
from prism_agent_kit.core.ports import ModelRequest

router = APIRouter(prefix="/model-profiles", tags=["model-profiles"])


def _to_input(payload: ModelProfileCreate) -> ModelProfileInput:
    return ModelProfileInput(**payload.model_dump())


def _to_view(profile: ModelProfile) -> ModelProfileView:
    return ModelProfileView(
        id=profile.id,
        name=profile.name,
        base_url=profile.base_url,
        model=profile.model,
        api_key_env=profile.api_key_env,
        context_window=profile.context_window,
        max_output_tokens=profile.max_output_tokens,
        is_active=profile.is_active,
    )


@router.get("", response_model=list[ModelProfileView])
async def list_profiles(service: ModelProfileServiceDependency) -> list[ModelProfileView]:
    """返回全部档案与激活标记。"""
    return [_to_view(profile) for profile in await service.list()]


@router.post("", response_model=ModelProfileView)
async def create_profile(
    payload: ModelProfileCreate, service: ModelProfileServiceDependency
) -> ModelProfileView:
    """新增模型档案。"""
    return _to_view(await service.create(_to_input(payload)))


@router.patch("/{profile_id}", response_model=ModelProfileView)
async def update_profile(
    profile_id: str,
    payload: ModelProfileCreate,
    service: ModelProfileServiceDependency,
) -> ModelProfileView:
    """更新模型档案。"""
    return _to_view(await service.update(profile_id, _to_input(payload)))


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, service: ModelProfileServiceDependency) -> None:
    """删除模型档案（激活中的档案需先切换）。"""
    await service.delete(profile_id)


@router.post("/{profile_id}/activate", response_model=ModelProfileView)
async def activate_profile(
    profile_id: str, service: ModelProfileServiceDependency
) -> ModelProfileView:
    """全局切换到该档案；下一次请求起生效。"""
    return _to_view(await service.activate(profile_id))


@router.post("/{profile_id}/probe", response_model=ModelProfileProbeView)
async def probe_profile(
    profile_id: str,
    service: ModelProfileServiceDependency,
    factory: ProviderFactoryDependency,
) -> ModelProfileProbeView:
    """用目标档案发一次最小请求，验证连通性。"""
    profile = await service.get(profile_id)
    started = time.perf_counter()
    try:
        provider = factory.build(profile)
        await provider.stream(
            ModelRequest(
                system_prompt="ping",
                messages=[
                    Message(
                        session_id="probe",
                        run_id="probe",
                        role=MessageRole.USER,
                        content="ping",
                    )
                ],
                max_output_tokens=8,
            )
        )
    except AgentKitError as error:
        return ModelProfileProbeView(ok=False, latency_ms=None, error=error.message)
    except Exception as error:
        return ModelProfileProbeView(ok=False, latency_ms=None, error=type(error).__name__)
    return ModelProfileProbeView(
        ok=True,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        error=None,
    )
