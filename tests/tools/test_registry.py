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
