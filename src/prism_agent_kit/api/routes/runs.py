from fastapi import APIRouter

from prism_agent_kit.api.schemas import RunCreate, RunView
from prism_agent_kit.application.run_service import RunService


def create_runs_router(service: RunService) -> APIRouter:
    """创建 Run 相关路由。"""
    router = APIRouter(tags=["runs"])

    @router.post(
        "/sessions/{session_id}/runs",
        response_model=RunView,
        status_code=202,
        summary="创建 Run",
    )
    async def create_run(session_id: str, payload: RunCreate) -> RunView:
        run = await service.create(
            session_id,
            input_text=payload.input,
            prompt_ref=payload.prompt_ref,
            metadata=payload.metadata,
        )
        return RunView.from_domain(run)

    @router.get("/runs/{run_id}", response_model=RunView, summary="获取 Run")
    async def get_run(run_id: str) -> RunView:
        run = await service.get(run_id)
        return RunView.from_domain(run)

    return router
