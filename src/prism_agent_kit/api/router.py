from fastapi import APIRouter

from prism_agent_kit.api.routes import health
from prism_agent_kit.api.routes.runs import create_runs_router
from prism_agent_kit.api.routes.sessions import create_sessions_router
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService

api_router = APIRouter()
api_router.include_router(health.router)


def create_api_router(
    *,
    session_service: SessionService,
    run_service: RunService,
) -> APIRouter:
    """组装需要应用服务的完整 API 路由。"""
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(create_sessions_router(session_service))
    router.include_router(create_runs_router(run_service))
    return router
