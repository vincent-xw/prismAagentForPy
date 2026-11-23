from fastapi import APIRouter

from prism_agent_kit.api.routes import health
from prism_agent_kit.api.routes.runs import create_runs_router
from prism_agent_kit.api.routes.sessions import create_sessions_router
from prism_agent_kit.api.routes.tools import create_tools_router
from prism_agent_kit.api.routes.workspaces import create_workspaces_router


def create_api_router() -> APIRouter:
    """组装需要应用服务的完整 API 路由。"""
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(create_sessions_router())
    router.include_router(create_runs_router())
    router.include_router(create_tools_router())
    router.include_router(create_workspaces_router())
    return router


api_router = create_api_router()
