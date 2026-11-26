from pathlib import Path

import pytest
from tests.support.skill_helpers import make_skill

from prism_agent_kit.application.skills.catalog import SkillCatalog
from prism_agent_kit.application.skills.package import SkillError
from prism_agent_kit.core.errors import ErrorCode


def test_root_precedence(tmp_path: Path) -> None:
    prism, agents = tmp_path / "prism", tmp_path / "agent"
    make_skill(prism, "pdf", "prism version")
    make_skill(agents, "pdf", "agent version")

    catalog = SkillCatalog([prism, agents])
    skills = catalog.list_skills()

    winners = [s for s in skills if s.name == "pdf" and not s.shadowed]
    assert [s.description for s in winners] == ["prism version"]
    assert [s.description for s in skills if s.name == "pdf" and s.shadowed] == ["agent version"]
    assert "pdf" in catalog.render_catalog()


def test_catalog_budget(tmp_path: Path) -> None:
    for index in range(60):
        make_skill(tmp_path, f"skill-{index}", "x" * 300)

    text = SkillCatalog([tmp_path], max_chars=1200).render_catalog()

    assert len(text) <= 1200
    assert "已省略" in text


def test_missing_skill(tmp_path: Path) -> None:
    with pytest.raises(SkillError) as error:
        SkillCatalog([tmp_path]).get("nope")
    assert error.value.code is ErrorCode.SKILL_NOT_FOUND
