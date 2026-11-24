import pytest
from pydantic import BaseModel

from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.tools.contracts import ToolDefinition
from prism_agent_kit.tools.registry import ToolRegistry


class DemoInput(BaseModel):
    value: str


def test_tool_schema_requires_object_input() -> None:
    definition = ToolDefinition(
        name="bad",
        description="bad",
        input_model=str,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=1,
    )

    with pytest.raises(AgentKitError) as error:
        definition.to_model_schema()

    assert error.value.code is ErrorCode.INVALID_TOOL_DEFINITION


def test_registry_rejects_duplicate_tool_names() -> None:
    registry = ToolRegistry()
    definition = ToolDefinition(
        name="demo",
        description="demo",
        input_model=DemoInput,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=1,
    )
    registry.register(definition)

    with pytest.raises(AgentKitError) as error:
        registry.register(definition)

    assert error.value.code is ErrorCode.INVALID_TOOL_DEFINITION


def test_registry_lists_openai_tool_schemas() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="demo",
            description="demo",
            input_model=DemoInput,
            output_model=None,
            execution_mode=ExecutionMode.LOCAL,
            timeout_seconds=1,
        )
    )

    schemas = registry.model_schemas()

    assert schemas[0]["type"] == "function"
    function = schemas[0]["function"]
    assert isinstance(function, dict)
    assert function["name"] == "demo"
    assert function["parameters"]["type"] == "object"


def test_missing_tool_raises_not_found() -> None:
    registry = ToolRegistry()

    with pytest.raises(AgentKitError) as error:
        registry.get("missing")

    assert error.value.code is ErrorCode.TOOL_NOT_FOUND
    assert error.value.http_status == 404


def test_input_schema_override_wins() -> None:
    from pydantic import BaseModel

    from prism_agent_kit.core.enums import ExecutionMode
    from prism_agent_kit.tools.contracts import ToolDefinition

    class In(BaseModel):
        text: str

    override = {"type": "object", "properties": {"q": {"type": "string"}}, "$defs": {"X": {}}}
    definition = ToolDefinition(
        name="mcp__demo__search",
        description="d",
        input_model=In,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=5,
        input_schema_override=override,
    )

    parameters = definition.to_model_schema()["function"]["parameters"]
    assert parameters["$defs"] == {"X": {}}
    assert "q" in parameters["properties"]


def test_unregister_by_prefix() -> None:
    from prism_agent_kit.core.enums import ExecutionMode
    from prism_agent_kit.tools.contracts import ToolDefinition

    class In(BaseModel):
        text: str

    def make(name: str) -> ToolDefinition:
        return ToolDefinition(
            name=name,
            description="d",
            input_model=In,
            output_model=None,
            execution_mode=ExecutionMode.LOCAL,
            timeout_seconds=5,
        )

    registry = ToolRegistry()
    registry.register(make("mcp__a__x"))
    registry.register(make("mcp__a__y"))
    registry.register(make("echo"))

    removed = registry.unregister_by_prefix("mcp__a__")

    assert sorted(removed) == ["mcp__a__x", "mcp__a__y"]
    assert [tool.name for tool in registry.list_tools()] == ["echo"]
