"""工作区路径安全校验：所有文件访问都必须先经过这里。"""

import os
from pathlib import Path

from prism_agent_kit.core.errors import AgentKitError, ErrorCode

EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {".git", "node_modules", "dist", "build", ".dart_tool", "coverage"}
)


def resolve_in_workspace(root: str | Path, rel: str | None) -> Path:
    """把相对路径解析为工作区内的绝对路径；越界、绝对路径与符号链接逃逸一律拒绝。"""
    if rel is not None and "\x00" in rel:
        raise AgentKitError(
            ErrorCode.WORKSPACE_PATH_INVALID,
            "路径包含非法字符",
            http_status=400,
            details={"path": rel},
        )

    real_root = Path(root).expanduser().resolve()
    candidate = (real_root / (rel or "")).resolve(strict=False)
    try:
        inside = os.path.commonpath([str(candidate), str(real_root)]) == str(real_root)
    except ValueError:
        inside = False
    if not inside:
        raise AgentKitError(
            ErrorCode.WORKSPACE_PATH_OUTSIDE,
            "路径不在工作区范围内",
            http_status=403,
            details={"path": rel},
        )
    return candidate
