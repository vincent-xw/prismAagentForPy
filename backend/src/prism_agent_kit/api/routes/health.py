from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from prism_agent_kit import __version__
from prism_agent_kit.core.config import Settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    workspace_fts: Literal["ok", "unsupported"]


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def read_health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    container = request.app.state.container
    fts_ok = bool(getattr(container, "workspace_fts_supported", False))
    return HealthResponse(
        workspace_fts="ok" if fts_ok else "unsupported",
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )
