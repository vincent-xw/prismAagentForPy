"""技能列表与详情接口。"""

import asyncio

from fastapi import APIRouter

from prism_agent_kit.api.dependencies import SkillCatalogDependency
from prism_agent_kit.api.schemas import SkillDetailView, SkillsView, SkillView

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillsView)
async def list_skills(catalog: SkillCatalogDependency) -> SkillsView:
    """返回全部技能条目（含被同名遮蔽项）。"""
    return SkillsView(
        items=[
            SkillView(
                name=item.name,
                description=item.description,
                path=item.path,
                root=item.root,
                shadowed=item.shadowed,
            )
            for item in await asyncio.to_thread(catalog.list_skills)
        ]
    )


@router.get("/{name}", response_model=SkillDetailView)
async def get_skill(name: str, catalog: SkillCatalogDependency) -> SkillDetailView:
    """返回单个技能的正文与资源清单。"""
    package = await asyncio.to_thread(catalog.get, name)
    return SkillDetailView(
        name=package.name,
        description=package.description,
        content=package.body,
        resources=[
            {"path": resource.path, "kind": resource.kind, "bytes": resource.bytes}
            for resource in package.resources
        ],
    )
