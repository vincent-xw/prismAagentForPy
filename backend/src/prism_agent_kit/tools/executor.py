import asyncio
import inspect
import json
from typing import Any, cast

from pydantic import BaseModel, JsonValue, ValidationError

from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.tools.contracts import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)


class LocalToolExecutor:
    """执行本地工具并把运行异常转换为结构化结果。"""

    async def execute(
        self,
        definition: ToolDefinition,
        raw_input: JsonValue,
        context: ToolExecutionContext,
        *,
        timeout_seconds: float | None = None,
    ) -> ToolExecutionResult:
        """校验输入、执行工具并校验输出。"""
        if context.cancel.is_set():
            return ToolExecutionResult.failure(
                ErrorCode.RUN_CANCELLED,
                "工具执行已取消",
            )
        if definition.execution_mode is not ExecutionMode.LOCAL:
            return ToolExecutionResult.failure(
                ErrorCode.INVALID_TOOL_DEFINITION,
                "远端工具不能由本地执行器执行",
            )
        if definition.handler is None:
            return ToolExecutionResult.failure(
                ErrorCode.INVALID_TOOL_DEFINITION,
                "本地工具缺少执行函数",
            )
        try:
            definition.to_model_schema()
        except AgentKitError as error:
            return ToolExecutionResult.failure(error.code, error.message)

        try:
            validated_input = definition.input_model.model_validate(raw_input)
        except ValidationError:
            return ToolExecutionResult.failure(
                ErrorCode.TOOL_INPUT_INVALID,
                "工具输入不符合 Schema",
            )

        effective_timeout = (
            timeout_seconds if timeout_seconds is not None else definition.timeout_seconds
        )
        try:
            async with asyncio.timeout(effective_timeout):
                if inspect.iscoroutinefunction(definition.handler):
                    raw_output = await definition.handler(validated_input, context)
                else:
                    raw_output = await asyncio.to_thread(
                        definition.handler,
                        validated_input,
                        context,
                    )
        except TimeoutError:
            return ToolExecutionResult.failure(
                ErrorCode.TOOL_EXECUTION_TIMEOUT,
                "工具执行超时",
            )
        except asyncio.CancelledError:
            return ToolExecutionResult.failure(
                ErrorCode.RUN_CANCELLED,
                "工具执行已取消",
            )
        except AgentKitError as error:
            # 领域异常携带稳定错误码与安全文案，原样回传给模型与界面。
            return ToolExecutionResult.failure(error.code, error.message)
        except Exception:
            # 其他异常不透传正文。避免把内部细节写入历史或 API 响应。
            return ToolExecutionResult.failure(
                ErrorCode.TOOL_EXECUTION_FAILED,
                "工具执行失败",
            )

        try:
            output = self._validate_output(definition, raw_output)
        except (TypeError, ValueError):
            return ToolExecutionResult.failure(
                ErrorCode.TOOL_OUTPUT_INVALID,
                "工具输出不符合 Schema",
            )
        return ToolExecutionResult.success(output)

    @staticmethod
    def _validate_output(
        definition: ToolDefinition,
        raw_output: Any,
    ) -> JsonValue:
        """把工具返回值规范化为 JSON 值。"""
        if definition.output_model is not None:
            if isinstance(raw_output, definition.output_model):
                validated = raw_output
            else:
                validated = definition.output_model.model_validate(raw_output)
            return cast(JsonValue, validated.model_dump(mode="json"))
        if isinstance(raw_output, BaseModel):
            return cast(JsonValue, raw_output.model_dump(mode="json"))
        serialized = json.dumps(raw_output, ensure_ascii=False, allow_nan=False)
        return cast(JsonValue, json.loads(serialized))
