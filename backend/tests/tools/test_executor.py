import asyncio
from threading import get_ident

from pydantic import BaseModel

from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.core.errors import ErrorCode
from prism_agent_kit.tools.contracts import (
    ToolDefinition,
    ToolExecutionContext,
)
from prism_agent_kit.tools.executor import LocalToolExecutor


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    text: str


class InvalidOutput(BaseModel):
    count: int


async def echo_handler(input: EchoInput, context: ToolExecutionContext) -> EchoOutput:
    return EchoOutput(text=input.text)


async def slow_handler(input: EchoInput, context: ToolExecutionContext) -> EchoOutput:
    await asyncio.sleep(0.1)
    return EchoOutput(text=input.text)


async def invalid_output_handler(
    input: EchoInput,
    context: ToolExecutionContext,
) -> dict[str, str]:
    return {"text": input.text}


MAIN_THREAD_ID = get_ident()


def sync_handler(input: EchoInput, context: ToolExecutionContext) -> EchoOutput:
    return EchoOutput(text=f"{input.text}:{get_ident() != MAIN_THREAD_ID}")


def make_context(cancel: asyncio.Event | None = None) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="run-1",
        session_id="session-1",
        call_id="call-1",
        cancel=cancel or asyncio.Event(),
    )


def make_definition(
    handler: object,
    *,
    output_model: type[BaseModel] | None = EchoOutput,
) -> ToolDefinition:
    return ToolDefinition(
        name="demo",
        description="demo",
        input_model=EchoInput,
        output_model=output_model,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=1,
        handler=handler,
    )


async def test_local_tool_success_validates_input_and_output() -> None:
    result = await LocalToolExecutor().execute(
        make_definition(echo_handler),
        {"text": "hi"},
        make_context(),
    )

    assert result.ok is True
    assert result.output == {"text": "hi"}


async def test_tool_input_error_is_returned_as_contract_error() -> None:
    result = await LocalToolExecutor().execute(
        make_definition(echo_handler),
        {"missing": "value"},
        make_context(),
    )

    assert result.ok is False
    assert result.error_code is ErrorCode.TOOL_INPUT_INVALID


async def test_local_tool_timeout_returns_tool_error() -> None:
    result = await LocalToolExecutor().execute(
        make_definition(slow_handler),
        {"text": "hi"},
        make_context(),
        timeout_seconds=0.01,
    )

    assert result.ok is False
    assert result.error_code is ErrorCode.TOOL_EXECUTION_TIMEOUT


async def test_tool_output_error_is_returned_as_contract_error() -> None:
    result = await LocalToolExecutor().execute(
        make_definition(invalid_output_handler, output_model=InvalidOutput),
        {"text": "hi"},
        make_context(),
    )

    assert result.ok is False
    assert result.error_code is ErrorCode.TOOL_OUTPUT_INVALID


async def test_sync_tool_runs_in_worker_thread() -> None:
    result = await LocalToolExecutor().execute(
        make_definition(sync_handler),
        {"text": "hi"},
        make_context(),
    )

    assert result.ok is True
    assert result.output == {"text": "hi:True"}


async def test_cancelled_context_returns_run_cancelled() -> None:
    cancel = asyncio.Event()
    cancel.set()

    result = await LocalToolExecutor().execute(
        make_definition(echo_handler),
        {"text": "hi"},
        make_context(cancel),
    )

    assert result.ok is False
    assert result.error_code is ErrorCode.RUN_CANCELLED


async def test_executor_preserves_domain_error_code() -> None:
    """工具内部抛出的领域异常必须保留错误码与消息，而不是被吞成通用失败。"""
    from prism_agent_kit.core.errors import AgentKitError, ErrorCode

    async def handler(_raw: object, _context: object) -> None:
        raise AgentKitError(ErrorCode.WORKSPACE_NOT_BOUND, "尚未绑定工作区", http_status=409)

    definition = ToolDefinition(
        name="boom",
        description="boom",
        input_model=EchoInput,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=5,
        handler=handler,
    )
    result = await LocalToolExecutor().execute(
        definition,
        {"text": "x"},
        ToolExecutionContext(run_id="r", session_id="s", call_id="c", cancel=asyncio.Event()),
    )

    assert result.ok is False
    assert result.error_code is ErrorCode.WORKSPACE_NOT_BOUND
    assert result.error_message == "尚未绑定工作区"
