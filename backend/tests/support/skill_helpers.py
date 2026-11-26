from pathlib import Path


def make_skill(
    root: Path,
    name: str,
    description: str = "demo skill",
    body: str = "# Instructions\nDo the thing.",
    resources: dict[str, str] | None = None,
) -> Path:
    directory = root / name
    (directory / "references").mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}",
        encoding="utf-8",
    )
    for rel_path, content in (resources or {}).items():
        target = directory / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return directory
