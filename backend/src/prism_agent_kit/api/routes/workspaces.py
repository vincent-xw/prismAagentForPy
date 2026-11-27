from fastapi import APIRouter

from prism_agent_kit.api.dependencies import WorkspaceServiceDependency
from prism_agent_kit.api.schemas import (
    FileView,
    SearchHitView,
    SearchResponse,
    TreeEntryView,
    TreeResponse,
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspacePickResponse,
    WorkspaceUpdate,
    WorkspaceView,
)


def create_workspaces_router() -> APIRouter:
    """创建工作区相关路由。"""
    router = APIRouter(tags=["workspaces"])

    @router.get("/workspaces", response_model=WorkspaceListResponse, summary="列出工作区")
    async def list_workspaces(service: WorkspaceServiceDependency) -> WorkspaceListResponse:
        items = await service.list_workspaces()
        active = next((item for item in items if item.is_active), None)
        return WorkspaceListResponse(
            items=[WorkspaceView.from_domain(item) for item in items],
            active_id=active.id if active is not None else None,
        )

    @router.post("/workspaces/pick", response_model=WorkspacePickResponse, summary="选择目录")
    async def pick_workspace(service: WorkspaceServiceDependency) -> WorkspacePickResponse:
        return WorkspacePickResponse(path=await service.pick_directory())

    @router.post("/workspaces", response_model=WorkspaceView, summary="绑定并激活工作区")
    async def create_workspace(
        payload: WorkspaceCreate,
        service: WorkspaceServiceDependency,
    ) -> WorkspaceView:
        workspace = await service.create(
            payload.path,
            label=payload.label,
            name=payload.name,
            permission_mode=payload.permission_mode,
        )
        return WorkspaceView.from_domain(workspace)

    @router.patch(
        "/workspaces/{workspace_id}", response_model=WorkspaceView, summary="更新工作区档位"
    )
    async def update_workspace(
        workspace_id: str,
        payload: WorkspaceUpdate,
        service: WorkspaceServiceDependency,
    ) -> WorkspaceView:
        workspace = await service.get(workspace_id)
        if payload.permission_mode is not None:
            workspace = await service.update_permission(workspace_id, payload.permission_mode)
        return WorkspaceView.from_domain(workspace)

    @router.get("/workspaces/{workspace_id}", response_model=WorkspaceView, summary="获取工作区")
    async def get_workspace(
        workspace_id: str,
        service: WorkspaceServiceDependency,
    ) -> WorkspaceView:
        return WorkspaceView.from_domain(await service.get(workspace_id))

    @router.post(
        "/workspaces/{workspace_id}/activate",
        response_model=WorkspaceView,
        summary="切换活跃工作区",
    )
    async def activate_workspace(
        workspace_id: str,
        service: WorkspaceServiceDependency,
    ) -> WorkspaceView:
        return WorkspaceView.from_domain(await service.activate(workspace_id))

    @router.post(
        "/workspaces/{workspace_id}/reindex",
        response_model=WorkspaceView,
        summary="重建索引",
    )
    async def reindex_workspace(
        workspace_id: str,
        service: WorkspaceServiceDependency,
    ) -> WorkspaceView:
        return WorkspaceView.from_domain(await service.reindex(workspace_id))

    @router.delete("/workspaces/{workspace_id}", status_code=204, summary="删除工作区绑定")
    async def delete_workspace(
        workspace_id: str,
        service: WorkspaceServiceDependency,
    ) -> None:
        await service.delete(workspace_id)

    @router.get(
        "/workspaces/{workspace_id}/tree",
        response_model=TreeResponse,
        summary="列出目录",
    )
    async def read_tree(
        workspace_id: str,
        service: WorkspaceServiceDependency,
        path: str = ".",
    ) -> TreeResponse:
        entries = await service.tree(workspace_id, path)
        return TreeResponse(
            items=[
                TreeEntryView(
                    name=entry.name,
                    type=entry.type,
                    size=entry.size,
                    modified_at=entry.modified_at,
                )
                for entry in entries
            ]
        )

    @router.get(
        "/workspaces/{workspace_id}/file",
        response_model=FileView,
        summary="读取文本文件",
    )
    async def read_file(
        workspace_id: str,
        service: WorkspaceServiceDependency,
        path: str,
        max_bytes: int = 65_536,
    ) -> FileView:
        content = await service.read_file(workspace_id, path, max_bytes=max_bytes)
        return FileView(
            path=path,
            content=content.content,
            truncated=content.truncated,
            size=content.size,
        )

    @router.get(
        "/workspaces/{workspace_id}/search",
        response_model=SearchResponse,
        summary="检索工作区",
    )
    async def search_workspace(
        workspace_id: str,
        service: WorkspaceServiceDependency,
        q: str,
        limit: int = 20,
        path_prefix: str | None = None,
    ) -> SearchResponse:
        hits = await service.search(workspace_id, q, limit=limit, path_prefix=path_prefix)
        return SearchResponse(
            items=[SearchHitView(path=hit.path, snippet=hit.snippet) for hit in hits]
        )

    return router
