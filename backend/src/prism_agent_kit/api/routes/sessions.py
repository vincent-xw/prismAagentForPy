from fastapi import APIRouter

from prism_agent_kit.api.dependencies import SessionServiceDependency
from prism_agent_kit.api.schemas import (
    MessageListResponse,
    MessageView,
    SessionCreate,
    SessionListResponse,
    SessionView,
    SessionWorkspaceUpdate,
)


def create_sessions_router() -> APIRouter:
    """创建 Session 查询路由。"""
    router = APIRouter(tags=["sessions"])

    @router.post("/sessions", response_model=SessionView, status_code=201, summary="创建 Session")
    async def create_session(
        payload: SessionCreate,
        service: SessionServiceDependency,
    ) -> SessionView:
        session = await service.create(payload.title)
        return SessionView.from_domain(session)

    @router.post(
        "/sessions/{session_id}/workspace",
        response_model=SessionView,
        summary="绑定会话工作区",
    )
    async def bind_session_workspace(
        session_id: str,
        payload: SessionWorkspaceUpdate,
        service: SessionServiceDependency,
    ) -> SessionView:
        session = await service.set_workspace(session_id, payload.workspace_id)
        return SessionView.from_domain(session)

    @router.get("/sessions", response_model=SessionListResponse, summary="列出 Session")
    async def list_sessions(service: SessionServiceDependency) -> SessionListResponse:
        sessions = await service.list()
        return SessionListResponse(items=[SessionView.from_domain(item) for item in sessions])

    @router.get("/sessions/{session_id}", response_model=SessionView, summary="获取 Session")
    async def get_session(
        session_id: str,
        service: SessionServiceDependency,
    ) -> SessionView:
        session = await service.get(session_id)
        return SessionView.from_domain(session)

    @router.get(
        "/sessions/{session_id}/messages",
        response_model=MessageListResponse,
        summary="获取 Session 消息",
    )
    async def list_messages(
        session_id: str,
        service: SessionServiceDependency,
    ) -> MessageListResponse:
        messages = await service.list_messages(session_id)
        return MessageListResponse(items=[MessageView.from_domain(item) for item in messages])

    return router
