from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, JsonValue

from prism_agent_kit.core.enums import MessageKind, MessageRole
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, ToolCall
from prism_agent_kit.core.token_budget import TokenEstimator


class ContextAssembly(BaseModel):
    """本次模型请求可使用的上下文快照。"""

    messages: list[Message]
    estimated_tokens: int
    trimmed_count: int
    trimmed_tokens: int = 0


class ContextAssembler:
    """按完整消息组裁剪历史并计算输入预算。"""

    def __init__(
        self,
        estimator: TokenEstimator,
        *,
        context_window: int,
        max_output_tokens: int,
        safety_margin_tokens: int,
    ) -> None:
        self._estimator = estimator
        self._input_budget = context_window - max_output_tokens - safety_margin_tokens
        if self._input_budget <= 0:
            raise AgentKitError(
                ErrorCode.CONTEXT_BUDGET_EXCEEDED,
                "模型上下文预算必须为正数",
                http_status=422,
            )

    @property
    def input_budget(self) -> int:
        """模型输入的 token 预算。"""
        return self._input_budget

    @property
    def estimator(self) -> TokenEstimator:
        """组装器使用的 token 估算器。"""
        return self._estimator

    def estimate_tokens(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tool_calls: Sequence[ToolCall] = (),
        tool_schemas: Sequence[JsonValue] = (),
    ) -> int:
        """按 assembler 相同的口径估算当前输入 token。"""
        units = self._build_units(list(messages), tool_calls)
        fixed_tokens = self._estimator.count_text(system_prompt) + sum(
            self._estimator.count_json(schema) for schema in tool_schemas
        )
        return fixed_tokens + sum(
            sum(self._estimator.count_message(message) for message in unit_messages)
            + sum(self._estimator.count_tool_call(call) for call in unit_calls)
            for unit_messages, unit_calls, _protected in units
        )

    def assemble(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tool_calls: Sequence[ToolCall] = (),
        tool_schemas: Sequence[JsonValue] = (),
    ) -> ContextAssembly:
        """组装上下文。只从最旧的完整消息组开始裁剪。"""
        if not messages:
            raise AgentKitError(
                ErrorCode.INVALID_HISTORY,
                "上下文缺少消息历史",
                http_status=500,
            )

        units = self._build_units(list(messages), tool_calls)
        fixed_tokens = self._estimator.count_text(system_prompt) + sum(
            self._estimator.count_json(schema) for schema in tool_schemas
        )
        if fixed_tokens > self._input_budget:
            raise AgentKitError(
                ErrorCode.CONTEXT_BUDGET_EXCEEDED,
                "System Prompt 或工具 Schema 超出上下文预算",
                http_status=422,
                details={"input_budget": self._input_budget},
            )

        unit_tokens = [
            sum(self._estimator.count_message(message) for message in unit_messages)
            + sum(self._estimator.count_tool_call(tool_call) for tool_call in unit_tool_calls)
            for unit_messages, unit_tool_calls, _protected in units
        ]
        total_tokens = fixed_tokens + sum(unit_tokens)
        trimmed_count = 0
        trimmed_tokens = 0

        while total_tokens > self._input_budget:
            removable = [
                index for index, (_unit, _calls, protected) in enumerate(units) if not protected
            ]
            # 至少保留最后一条非保护单元（当前用户输入），受保护单元永不裁剪。
            if len(removable) <= 1:
                break
            removed_index = removable[0]
            removed_unit, _removed_calls, _ = units.pop(removed_index)
            removed_tokens = unit_tokens.pop(removed_index)
            total_tokens -= removed_tokens
            trimmed_count += len(removed_unit)
            trimmed_tokens += removed_tokens

        if total_tokens > self._input_budget:
            raise AgentKitError(
                ErrorCode.CONTEXT_BUDGET_EXCEEDED,
                "当前用户输入超出上下文预算",
                http_status=422,
                details={
                    "input_budget": self._input_budget,
                    "estimated_tokens": total_tokens,
                },
            )

        return ContextAssembly(
            messages=[message for unit, _calls, _protected in units for message in unit],
            estimated_tokens=total_tokens,
            trimmed_count=trimmed_count,
            trimmed_tokens=trimmed_tokens,
        )

    def _build_units(
        self,
        messages: list[Message],
        tool_calls: Sequence[ToolCall],
    ) -> list[tuple[list[Message], list[ToolCall], bool]]:
        """把 assistant 与其全部 tool 结果组成不可拆分单元；技能上下文标记为受保护。"""
        calls_by_assistant: dict[int, list[ToolCall]] = {}
        for tool_call in tool_calls:
            calls_by_assistant.setdefault(
                tool_call.assistant_message_id,
                [],
            ).append(tool_call)

        units: list[tuple[list[Message], list[ToolCall], bool]] = []
        index = 0
        while index < len(messages):
            message = messages[index]
            if message.role is MessageRole.USER:
                units.append(
                    (
                        [message],
                        [],
                        message.kind in (MessageKind.SKILL_CONTEXT, MessageKind.CHECKPOINT),
                    )
                )
                index += 1
                continue
            if message.role is MessageRole.TOOL:
                self._raise_invalid_history("tool 消息缺少对应的 assistant 消息")

            expected_calls = (
                calls_by_assistant.get(message.id, []) if message.id is not None else []
            )
            expected_ids = [tool_call.id for tool_call in expected_calls]
            unit = [message]
            index += 1
            while index < len(messages) and messages[index].role is MessageRole.TOOL:
                unit.append(messages[index])
                index += 1

            tool_messages = unit[1:]
            if expected_ids or tool_messages:
                self._validate_tool_group(expected_ids, tool_messages)
            units.append((unit, expected_calls, False))
        return units

    def _validate_tool_group(
        self,
        expected_ids: list[str],
        tool_messages: list[Message],
    ) -> None:
        """校验 assistant 发起的每个调用都恰好有一条 tool 结果。"""
        actual_ids = [message.tool_call_id for message in tool_messages]
        if any(call_id is None for call_id in actual_ids):
            self._raise_invalid_history("tool 消息缺少 tool_call_id")
        expected_counter = Counter(expected_ids)
        actual_counter = Counter(actual_ids)
        if expected_counter != actual_counter:
            self._raise_invalid_history("assistant 与 tool 消息未闭合")

    @staticmethod
    def _raise_invalid_history(message: str) -> None:
        raise AgentKitError(
            ErrorCode.INVALID_HISTORY,
            message,
            http_status=500,
        )
