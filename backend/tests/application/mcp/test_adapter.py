import pytest
from mcp.types import CallToolResult, ImageContent, TextContent

from prism_agent_kit.application.mcp.adapter import (
    McpToolInfo,
    normalize_result,
    to_tool_definition,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.mcp import McpServer


def make_server() -> McpServer:
    return McpServer(name="demo", transport="stdio", command="python")


async def test_definition_passes_schema_and_requires_approval() -> None:
    captured: dict[str, object] = {}

    async def invoke(name: str, arguments: dict[str, object]) -> dict[str, object]:
        captured["name"] = name
        captured["arguments"] = arguments
        return {"ok": True}

    definition = to_tool_definition(
        make_server(),
        McpToolInfo(
            name="search",
            description="d",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}, "$defs": {}},
        ),
        invoke,
        timeout_seconds=30,
    )

    assert definition.name == "mcp__demo__search"
    assert definition.requires_approval is True
    assert definition.to_model_schema()["function"]["parameters"]["$defs"] == {}
    output = await definition.handler(definition.input_model(query="x"), None)
    assert output == {"ok": True}
    assert captured["name"] == "mcp__demo__search"
    assert captured["arguments"] == {"query": "x"}


def test_normalize_result_text_truncate_and_images() -> None:
    result = CallToolResult(
        content=[
            TextContent(type="text", text="x" * 300_000),
            ImageContent(type="image", data="AAAA", mime_type="image/png"),
        ],
        is_error=False,
    )
    value = normalize_result(result, 204_800)
    assert value["truncated"] is True
    assert len(value["text"].encode("utf-8")) <= 204_800
    assert value["images"] == [{"type": "image", "mimeType": "image/png", "size": 3}]


def test_normalize_result_structured_and_error() -> None:
    ok = CallToolResult(
        content=[TextContent(type="text", text="hi")], structured_content={"a": 1}, is_error=False
    )
    assert normalize_result(ok, 1000)["structured"] == {"a": 1}

    bad = CallToolResult(content=[TextContent(type="text", text="boom")], is_error=True)
    with pytest.raises(AgentKitError) as error:
        normalize_result(bad, 1000)
    assert error.value.code is ErrorCode.MCP_TOOL_ERROR


def test_normalize_result_truncates_structured() -> None:
    result = CallToolResult(
        content=[TextContent(type="text", text="ok")],
        structured_content={"blob": "y" * 300_000},
        is_error=False,
    )
    value = normalize_result(result, 204_800)
    assert value["structured"] == {"truncated": True}
