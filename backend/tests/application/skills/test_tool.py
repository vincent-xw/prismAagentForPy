from pathlib import Path

import pytest
from tests.support.skill_helpers import make_skill

from prism_agent_kit.application.skills.catalog import SkillCatalog
from prism_agent_kit.application.skills.tools import SkillToolInput, build_skill_tool
from prism_agent_kit.core.errors import AgentKitError, ErrorCode


@pytest.fixture
def catalog(tmp_path: Path) -> SkillCatalog:
    make_skill(tmp_path, "pdf-tools", "Extract PDFs.", "# PDF tools", {"references/a.md": "# A"})
    return SkillCatalog([tmp_path])


async def test_load_skill_body(catalog: SkillCatalog) -> None:
    tool = build_skill_tool(catalog)

    output = await tool.handler(SkillToolInput(name="pdf-tools"), None)  # type: ignore[arg-type]

    assert "<skill_content" in output["content"]
    assert "PDF tools" in output["content"]
    assert output["truncated"] is False
    assert output["resources"][0]["path"] == "references/a.md"


async def test_read_resource_and_reject_escape(catalog: SkillCatalog) -> None:
    tool = build_skill_tool(catalog)

    output = await tool.handler(
        SkillToolInput(name="pdf-tools", path="references/a.md"),
        None,  # type: ignore[arg-type]
    )
    assert output["content"] == "# A"

    with pytest.raises(AgentKitError) as error:
        await tool.handler(
            SkillToolInput(name="pdf-tools", path="../../etc/passwd"),
            None,  # type: ignore[arg-type]
        )
    assert error.value.code is ErrorCode.SKILL_PATH_INVALID


async def test_unknown_skill(catalog: SkillCatalog) -> None:
    tool = build_skill_tool(catalog)
    with pytest.raises(AgentKitError) as error:
        await tool.handler(SkillToolInput(name="nope"), None)  # type: ignore[arg-type]
    assert error.value.code is ErrorCode.SKILL_NOT_FOUND


async def test_truncates_long_body(tmp_path: Path) -> None:
    make_skill(tmp_path, "big", "d", "x" * 500)
    tool = build_skill_tool(SkillCatalog([tmp_path]), max_chars=100)

    output = await tool.handler(SkillToolInput(name="big"), None)  # type: ignore[arg-type]
    assert output["truncated"] is True
    assert len(output["content"]) <= 100
