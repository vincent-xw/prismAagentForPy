"""技能包解析与资源读取。"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from prism_agent_kit.core.errors import AgentKitError, ErrorCode

logger = logging.getLogger(__name__)

_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RESOURCE_KINDS = ("references", "scripts", "assets")


class SkillError(AgentKitError):
    """技能相关的领域错误。"""


@dataclass(frozen=True)
class SkillResource:
    """技能目录内的一个资源文件。"""

    path: str
    kind: str
    bytes: int


@dataclass(frozen=True)
class SkillPackage:
    """解析后的技能包。"""

    name: str
    description: str
    body: str
    directory: Path
    root: Path
    resources: list[SkillResource] = field(default_factory=list)


def parse_skill(directory: Path, *, max_description: int = 1024) -> SkillPackage:
    """解析目录下的 SKILL.md，缺失或非法时抛 SkillError。"""
    skill_file = directory / "SKILL.md"
    if not skill_file.is_file():
        raise _error(ErrorCode.SKILL_INVALID, f"{directory} 缺少 SKILL.md")
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise _error(ErrorCode.SKILL_INVALID, f"无法读取 {skill_file}: {error}") from error

    frontmatter, body = _split_frontmatter(text)
    name = frontmatter.get("name", "").strip()
    description = frontmatter.get("description", "").strip()
    if _SKILL_NAME.fullmatch(name) is None or len(name) > 64:
        raise _error(ErrorCode.SKILL_INVALID, f"技能名非法: {name!r}")
    if not description or len(description) > max_description:
        raise _error(ErrorCode.SKILL_INVALID, f"技能 {name} 的 description 缺失或过长")
    if directory.name != name:
        logger.warning("技能目录名与 name 不一致: %s != %s", directory.name, name)

    return SkillPackage(
        name=name,
        description=description,
        body=body,
        directory=directory,
        root=directory.parent,
        resources=_scan_resources(directory),
    )


def render_skill_content(package: SkillPackage) -> str:
    """渲染注入给模型的 <skill_content> 块。"""
    return f'<skill_content name="{package.name}">\n{package.body}\n</skill_content>'


def read_text_resource(
    package: SkillPackage,
    rel_path: str,
    *,
    max_bytes: int = 204_800,
) -> str:
    """读取技能目录内的 UTF-8 文本资源，拒绝越界与超大文件。"""
    relative = Path(rel_path)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise _error(ErrorCode.SKILL_PATH_INVALID, f"非法资源路径: {rel_path}")
    base = package.directory.resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise _error(ErrorCode.SKILL_PATH_INVALID, f"资源不存在或越界: {rel_path}")
    if target.stat().st_size > max_bytes:
        raise _error(
            ErrorCode.SKILL_RESOURCE_TOO_LARGE,
            f"资源超过 {max_bytes} 字节: {rel_path}",
        )
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise _error(ErrorCode.SKILL_INVALID, f"资源不是 UTF-8 文本: {rel_path}") from error


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise _error(ErrorCode.SKILL_INVALID, "SKILL.md 缺少 frontmatter")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise _error(ErrorCode.SKILL_INVALID, "SKILL.md frontmatter 未闭合")
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line or line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values, "\n".join(lines[end + 1 :]).strip()


def _scan_resources(directory: Path) -> list[SkillResource]:
    resources: list[SkillResource] = []
    for kind in _RESOURCE_KINDS:
        base = directory / kind
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                resources.append(
                    SkillResource(
                        path=path.relative_to(directory).as_posix(),
                        kind=kind,
                        bytes=path.stat().st_size,
                    )
                )
    return resources


def _error(code: ErrorCode, message: str) -> SkillError:
    return SkillError(code, message, http_status=400)
