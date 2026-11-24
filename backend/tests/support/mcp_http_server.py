"""集成测试用的 Streamable HTTP MCP 服务。"""

import os

from mcp.server import MCPServer

server = MCPServer("http-test-server")


@server.tool()
def echo(text: str) -> str:
    """原样返回输入文本。"""
    return text


if __name__ == "__main__":
    server.run(transport="streamable-http", port=int(os.environ["PORT"]), stateless_http=True)
