from pydantic import JsonValue

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.tools.contracts import ToolDefinition


class ToolRegistry:
    """显式注册、不可动态扩展的工具注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> ToolDefinition:
        """注册工具。注册时立即校验名称与输入 Schema。"""
        definition.to_model_schema()
        if definition.name in self._tools:
            raise AgentKitError(
                ErrorCode.INVALID_TOOL_DEFINITION,
                "工具名已注册",
                http_status=400,
                details={"tool_name": definition.name},
            )
        self._tools[definition.name] = definition
        return definition

    def get(self, name: str) -> ToolDefinition:
        """按名称读取工具定义。"""
        definition = self._tools.get(name)
        if definition is None:
            raise AgentKitError(
                ErrorCode.TOOL_NOT_FOUND,
                "工具不存在",
                http_status=404,
                details={"tool_name": name},
            )
        return definition

    def list_tools(self) -> list[ToolDefinition]:
        """按注册顺序返回全部工具。"""
        return list(self._tools.values())

    def model_schemas(self) -> list[dict[str, JsonValue]]:
        """返回可直接发送给模型的工具声明。"""
        return [definition.to_model_schema() for definition in self._tools.values()]
