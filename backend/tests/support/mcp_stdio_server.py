"""集成测试用的最小 MCP stdio 服务。"""

import asyncio

from mcp.server import MCPServer

server = MCPServer("test-server")


@server.tool()
def echo(text: str) -> str:
    """原样返回输入文本。"""
    return text


@server.tool()
async def slow(seconds: float) -> str:
    """睡眠指定秒数，用于超时测试。"""
    await asyncio.sleep(seconds)
    return "done"


@server.tool()
def boom() -> str:
    """总是失败的工具。"""
    raise RuntimeError("boom")


if __name__ == "__main__":
    server.run()
