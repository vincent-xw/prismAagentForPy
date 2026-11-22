from fastapi import APIRouter

from prism_agent_kit.api.routes import health
from prism_agent_kit.api.routes.runs import create_runs_router
from prism_agent_kit.api.routes.sessions import create_sessions_router
from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService

api_router = APIRouter()
api_router.include_router(health.router)


def create_api_router(
    *,
    session_service: SessionService,
    run_service: RunService,
    event_bus: RunEventBus,
    test_mode: bool,
    heartbeat_seconds: float,
) -> APIRouter:
    """组装需要应用服务的完整 API 路由。"""
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(create_sessions_router(session_service))
    router.include_router(
        create_runs_router(
            run_service,
            event_bus=event_bus,
            test_mode=test_mode,
            heartbeat_seconds=heartbeat_seconds,
        )
    )
    return router
