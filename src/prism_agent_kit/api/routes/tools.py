from fastapi import APIRouter

from prism_agent_kit.api.schemas import ToolListResponse, ToolView
from prism_agent_kit.tools.registry import ToolRegistry


def create_tools_router(registry: ToolRegistry) -> APIRouter:
    """创建工具发现路由。"""
    router = APIRouter(tags=["tools"])

    @router.get("/tools", response_model=ToolListResponse, summary="列出工具")
    async def list_tools() -> ToolListResponse:
        return ToolListResponse(
            items=[ToolView.from_domain(definition) for definition in registry.list_tools()]
        )

    return router
