from pathlib import Path

import pytest
from tests.support.skill_helpers import make_skill

from prism_agent_kit.application.skills.package import (
    SkillError,
    parse_skill,
    read_text_resource,
)
from prism_agent_kit.core.errors import ErrorCode


def test_parse_valid(tmp_path: Path) -> None:
    make_skill(
        tmp_path,
        "pdf-tools",
        "Extract PDFs.",
        "# Hello\nread references/a.md",
        {"references/a.md": "# A"},
    )

    package = parse_skill(tmp_path / "pdf-tools")

    assert package.name == "pdf-tools"
    assert package.description == "Extract PDFs."
    assert package.body.startswith("# Hello")
    assert [resource.path for resource in package.resources] == ["references/a.md"]


def test_rejects_missing_frontmatter(tmp_path: Path) -> None:
    directory = tmp_path / "bad"
    directory.mkdir()
    (directory / "SKILL.md").write_text("no frontmatter", encoding="utf-8")

    with pytest.raises(SkillError) as error:
        parse_skill(directory)
    assert error.value.code is ErrorCode.SKILL_INVALID


def test_rejects_invalid_name_and_long_description(tmp_path: Path) -> None:
    make_skill(tmp_path, "Bad_Name", "d")
    with pytest.raises(SkillError):
        parse_skill(tmp_path / "Bad_Name")

    make_skill(tmp_path, "long", "x" * 1100)
    with pytest.raises(SkillError):
        parse_skill(tmp_path / "long")


def test_read_resource_and_reject_escape(tmp_path: Path) -> None:
    make_skill(tmp_path, "demo", "d", "body", {"references/a.md": "# A"})
    package = parse_skill(tmp_path / "demo")

    assert read_text_resource(package, "references/a.md") == "# A"

    with pytest.raises(SkillError) as error:
        read_text_resource(package, "../../etc/passwd")
    assert error.value.code is ErrorCode.SKILL_PATH_INVALID

    with pytest.raises(SkillError) as error:
        read_text_resource(package, str(tmp_path / "outside.txt"))
    assert error.value.code is ErrorCode.SKILL_PATH_INVALID


def test_resource_too_large(tmp_path: Path) -> None:
    make_skill(tmp_path, "demo", "d", "body", {"references/big.md": "x" * 300})
    package = parse_skill(tmp_path / "demo")

    with pytest.raises(SkillError) as error:
        read_text_resource(package, "references/big.md", max_bytes=100)
    assert error.value.code is ErrorCode.SKILL_RESOURCE_TOO_LARGE


def test_multiline_description_and_comments(tmp_path: Path) -> None:
    directory = tmp_path / "multi"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: multi\ndescription: |\n  line one\n  line two # keep\n---\nbody",
        encoding="utf-8",
    )

    package = parse_skill(directory)

    assert "line one" in package.description and "line two" in package.description


def test_rejects_symlink_package(tmp_path: Path) -> None:
    real = make_skill(tmp_path, "real", "d")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(SkillError) as error:
        parse_skill(link)
    assert error.value.code is ErrorCode.SKILL_INVALID
