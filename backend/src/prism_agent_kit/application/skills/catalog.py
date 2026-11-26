"""技能目录扫描、同名优先级与清单渲染。"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from prism_agent_kit.application.skills.package import SkillError, SkillPackage, parse_skill
from prism_agent_kit.core.errors import ErrorCode

logger = logging.getLogger(__name__)

_DESCRIPTION_LIMIT = 200


@dataclass(frozen=True)
class SkillSummary:
    """清单中的一个技能条目。"""

    name: str
    description: str
    path: str
    root: str
    shadowed: bool = False


class SkillCatalog:
    """按根目录优先级合并技能，并渲染带预算的清单。"""

    def __init__(
        self, roots: list[Path], *, max_chars: int = 8_000, cache_seconds: float = 5.0
    ) -> None:
        self._roots = [root.expanduser() for root in roots]
        self._max_chars = max_chars
        self._cache_seconds = cache_seconds
        self._cached_at = 0.0
        self._cached: list[SkillSummary] | None = None

    def list_skills(self, *, refresh: bool = False) -> list[SkillSummary]:
        """返回全部技能条目（含被同名遮蔽的 shadowed 项）。"""
        now = time.monotonic()
        if not refresh and self._cached is not None and now - self._cached_at < self._cache_seconds:
            return list(self._cached)
        summaries = self._scan()
        self._cached = summaries
        self._cached_at = now
        return list(summaries)

    def winners(self) -> list[SkillSummary]:
        """只返回未被遮蔽的技能。"""
        return [item for item in self.list_skills() if not item.shadowed]

    def get(self, name: str) -> SkillPackage:
        """按名称加载完整技能包。"""
        for summary in self.winners():
            if summary.name == name:
                return parse_skill(Path(summary.path))
        raise SkillError(
            ErrorCode.SKILL_NOT_FOUND,
            f"技能不存在: {name}",
            http_status=404,
            details={"name": name},
        )

    def render_catalog(self) -> str:
        """渲染 <available_skills> 块；空目录返回空串。"""
        entries = sorted(self.winners(), key=lambda item: item.name)
        if not entries:
            return ""

        def render(items: list[SkillSummary]) -> str:
            lines = [f"- {item.name}: {item.description} (path: {item.path})" for item in items]
            return "<available_skills>\n" + "\n".join(lines) + "\n</available_skills>"

        text = render(entries)
        if len(text) <= self._max_chars:
            return text

        clipped = [
            SkillSummary(
                name=item.name,
                description=item.description[:_DESCRIPTION_LIMIT],
                path=item.path,
                root=item.root,
            )
            for item in entries
        ]
        text = render(clipped)
        if len(text) <= self._max_chars:
            return text

        kept: list[SkillSummary] = []
        for item in clipped:
            candidate = render([*kept, item])
            if len(candidate) + 40 > self._max_chars:
                break
            kept.append(item)
        omitted = len(clipped) - len(kept)
        body = render(kept).removesuffix("\n</available_skills>")
        return f"{body}\n（已省略 {omitted} 个技能）\n</available_skills>"

    def _scan(self) -> list[SkillSummary]:
        summaries: list[SkillSummary] = []
        seen: set[str] = set()
        for root in self._roots:
            if not root.is_dir():
                continue
            try:
                directories = sorted(path for path in root.iterdir() if path.is_dir())
            except OSError as error:
                logger.warning("技能根目录不可读 %s: %s", root, error)
                continue
            for directory in directories:
                if not (directory / "SKILL.md").is_file():
                    continue
                try:
                    package = parse_skill(directory)
                except SkillError as error:
                    logger.warning("跳过非法技能 %s: %s", directory, error.message)
                    continue
                shadowed = package.name in seen
                if not shadowed:
                    seen.add(package.name)
                summaries.append(
                    SkillSummary(
                        name=package.name,
                        description=package.description,
                        path=str(directory),
                        root=str(root),
                        shadowed=shadowed,
                    )
                )
                if shadowed:
                    logger.info("技能 %s 被 %s 优先，忽略 %s", package.name, root, directory)
        return summaries
