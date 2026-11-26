"""`skill` 内置工具：按需加载技能正文与资源。"""

import asyncio

from pydantic import BaseModel, JsonValue

from prism_agent_kit.application.skills.catalog import SkillCatalog
from prism_agent_kit.application.skills.package import read_text_resource, render_skill_content
from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.tools.contracts import ToolDefinition, ToolExecutionContext

_DESCRIPTION = (
    "Load the full instructions for a skill. Call it before acting on a task that names "
    "or clearly matches a skill in the session skill catalog. Pass `path` to read a text "
    "resource bundled with the skill."
)


class SkillToolInput(BaseModel):
    """skill 工具入参。"""

    name: str
    path: str | None = None


def build_skill_tool(catalog: SkillCatalog, *, max_chars: int = 60_000) -> ToolDefinition:
    """构造只读的 `skill` 工具。"""

    async def handler(raw: SkillToolInput, _context: ToolExecutionContext) -> JsonValue:
        package = await asyncio.to_thread(catalog.get, raw.name)
        if raw.path is not None:
            content = read_text_resource(package, raw.path)
            resources: list[JsonValue] = []
        else:
            content = render_skill_content(package)
            resources = [
                {"path": resource.path, "kind": resource.kind, "bytes": resource.bytes}
                for resource in package.resources[:50]
            ]
        truncated = len(content) > max_chars
        return {
            "content": content[:max_chars],
            "resources": resources,
            "truncated": truncated,
        }

    return ToolDefinition(
        name="skill",
        description=_DESCRIPTION,
        input_model=SkillToolInput,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=30,
        requires_approval=False,
        handler=handler,
    )
