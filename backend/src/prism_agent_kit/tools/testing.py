from pydantic import BaseModel

from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.tools.contracts import ToolDefinition, ToolExecutionContext


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    text: str


async def _echo(input: EchoInput, context: ToolExecutionContext) -> EchoOutput:
    return EchoOutput(text=input.text)


class WaitForHostInput(BaseModel):
    value: str


def echo_tool() -> ToolDefinition:
    """返回用于本地循环测试的 echo 工具。"""
    return ToolDefinition(
        name="echo",
        description="返回输入文本",
        input_model=EchoInput,
        output_model=EchoOutput,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=5,
        handler=_echo,
    )


def wait_for_host_tool() -> ToolDefinition:
    """返回用于远端回填测试的 wait_for_host 工具。"""
    return ToolDefinition(
        name="wait_for_host",
        description="等待外部宿主回填结果",
        input_model=WaitForHostInput,
        output_model=None,
        execution_mode=ExecutionMode.REMOTE,
        timeout_seconds=300,
    )


ECHO_TOOL = echo_tool()
WAIT_FOR_HOST_TOOL = wait_for_host_tool()
