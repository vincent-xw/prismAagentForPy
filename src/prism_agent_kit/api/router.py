from fastapi import APIRouter

from prism_agent_kit.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
