"""MCP 工具名生成：带服务前缀、净化字符并在超长时追加哈希。"""

import hashlib
import re

MAX_TOOL_NAME = 64
_INVALID = re.compile(r"[^A-Za-z0-9_-]")


def tool_name_for(server_name: str, tool_name: str) -> str:
    """生成 `mcp__<server>__<tool>` 形式且不超过 64 字符的工具名。"""
    prefix = f"mcp__{server_name}__"
    safe = _INVALID.sub("_", tool_name)
    full = f"{prefix}{safe}"
    if len(full) <= MAX_TOOL_NAME:
        return full
    digest = hashlib.sha256(full.encode("utf-8")).hexdigest()[:6]
    keep = MAX_TOOL_NAME - len(prefix) - len("__") - len(digest)
    return f"{prefix}{safe[:keep]}__{digest}"
