from typing import Any

import pytest
from pydantic import JsonValue

from prism_agent_kit.core.context import ContextAssembler
from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import ExecutionMode, MessageKind, MessageRole
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, ToolCall


class FixedEstimator:
    """每条文本、JSON 与消息均按一个 token 计数的测试估算器。"""

    def count_text(self, text: str) -> int:
        return 1

    def count_json(self, value: JsonValue) -> int:
        return 1

    def count_message(self, message: Message) -> int:
        return 1

    def count_tool_call(self, tool_call: ToolCall) -> int:
        return 1


def make_message(
    message_id: int,
    role: MessageRole,
    content: Any,
    tool_call_id: str | None = None,
    kind: MessageKind = MessageKind.TEXT,
) -> Message:
    return Message(
        id=message_id,
        session_id="session-1",
        run_id="run-1",
        role=role,
        kind=kind,
        content=content,
        tool_call_id=tool_call_id,
    )


def make_tool_call(call_id: str, assistant_message_id: int = 2) -> ToolCall:
    return ToolCall(
        id=call_id,
        run_id="run-1",
        assistant_message_id=assistant_message_id,
        tool_name="demo",
        execution_mode=ExecutionMode.LOCAL,
        input={},
        input_digest=canonical_json_digest({}),
    )


def make_assembler() -> ContextAssembler:
    return ContextAssembler(
        estimator=FixedEstimator(),
        context_window=6,
        max_output_tokens=2,
        safety_margin_tokens=1,
    )


def test_context_trimming_keeps_assistant_and_tool_results_together() -> None:
    messages = [
        make_message(1, MessageRole.USER, "old"),
        make_message(2, MessageRole.ASSISTANT, None),
        make_message(3, MessageRole.TOOL, {"ok": True}, "call-1"),
        make_message(4, MessageRole.USER, "current"),
    ]

    assembly = make_assembler().assemble(
        system_prompt="system",
        messages=messages,
        tool_calls=[make_tool_call("call-1")],
    )

    assert [message.id for message in assembly.messages] == [4]
    assert assembly.trimmed_count == 3
    assert assembly.trimmed_tokens == 4
    assert assembly.estimated_tokens == 2


def test_incomplete_tool_group_fails_closed() -> None:
    messages = [
        make_message(1, MessageRole.USER, "hello"),
        make_message(2, MessageRole.ASSISTANT, None),
        make_message(3, MessageRole.TOOL, {"ok": True}, "call-1"),
        make_message(4, MessageRole.USER, "current"),
    ]

    with pytest.raises(AgentKitError) as error:
        make_assembler().assemble(
            system_prompt="system",
            messages=messages,
            tool_calls=[
                make_tool_call("call-1"),
                make_tool_call("call-2"),
            ],
        )

    assert error.value.code is ErrorCode.INVALID_HISTORY


def test_current_input_over_budget_fails_without_trimming_it() -> None:
    assembler = ContextAssembler(
        estimator=FixedEstimator(),
        context_window=3,
        max_output_tokens=1,
        safety_margin_tokens=1,
    )
    messages = [
        make_message(1, MessageRole.USER, "old"),
        make_message(2, MessageRole.USER, "current"),
    ]

    with pytest.raises(AgentKitError) as error:
        assembler.assemble(system_prompt="system", messages=messages)

    assert error.value.code is ErrorCode.CONTEXT_BUDGET_EXCEEDED


def test_tool_call_payload_counts_toward_budget() -> None:
    class ToolHeavyEstimator(FixedEstimator):
        def count_tool_call(self, tool_call: ToolCall) -> int:
            return 10

    assembler = ContextAssembler(
        estimator=ToolHeavyEstimator(),
        context_window=6,
        max_output_tokens=2,
        safety_margin_tokens=1,
    )

    with pytest.raises(AgentKitError) as error:
        assembler.assemble(
            system_prompt="system",
            messages=[
                make_message(2, MessageRole.ASSISTANT, None),
                make_message(3, MessageRole.TOOL, {"ok": True}, "call-1"),
            ],
            tool_calls=[make_tool_call("call-1")],
        )

    assert error.value.code is ErrorCode.CONTEXT_BUDGET_EXCEEDED


def make_small_assembler(window: int) -> ContextAssembler:
    return ContextAssembler(
        FixedEstimator(),
        context_window=window,
        max_output_tokens=1,
        safety_margin_tokens=1,
    )


def test_skill_context_never_trimmed() -> None:
    messages = [
        make_message(1, MessageRole.USER, "old"),
        make_message(2, MessageRole.USER, "skill", kind=MessageKind.SKILL_CONTEXT),
        make_message(3, MessageRole.USER, "current"),
    ]

    assembly = make_small_assembler(5).assemble(system_prompt="s", messages=messages)

    assert [message.id for message in assembly.messages] == [2, 3]
    assert assembly.messages[0].kind is MessageKind.SKILL_CONTEXT


def test_only_skill_context_over_budget_raises() -> None:
    messages = [
        make_message(1, MessageRole.USER, "skill", kind=MessageKind.SKILL_CONTEXT),
        make_message(2, MessageRole.USER, "current"),
    ]

    with pytest.raises(AgentKitError) as error:
        make_small_assembler(4).assemble(system_prompt="s", messages=messages)
    assert error.value.code is ErrorCode.CONTEXT_BUDGET_EXCEEDED
