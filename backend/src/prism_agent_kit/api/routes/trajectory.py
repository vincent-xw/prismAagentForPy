"""会话轨迹的只读接口。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from prism_agent_kit.api.dependencies import TrajectoryServiceDependency

router = APIRouter(prefix="/sessions", tags=["trajectory"])


@router.get("/{session_id}/trajectory")
async def get_trajectory(
    session_id: str,
    service: TrajectoryServiceDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[datetime | None, Query()] = None,
) -> dict[str, object]:
    """按 Turn → Step → Tool 返回轨迹投影。"""
    return await service.get(session_id, limit=limit, before=before)
