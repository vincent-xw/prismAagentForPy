"""本地联调用的示例 MCP 服务。

用法（在 UI 的 MCP 页添加 stdio 服务）：
  command: <仓库>/backend/.venv/bin/python
  args:    <仓库>/scripts/sample_mcp_server.py
"""

from datetime import datetime

from mcp.server import MCPServer

server = MCPServer("sample")


@server.tool()
def echo(text: str) -> str:
    """原样返回输入文本。"""
    return text


@server.tool()
def add(a: int, b: int) -> int:
    """返回两数之和。"""
    return a + b


@server.tool()
def now() -> str:
    """返回当前本地时间。"""
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    server.run()
