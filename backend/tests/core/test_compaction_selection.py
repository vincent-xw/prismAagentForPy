from prism_agent_kit.core.compaction import (
    PruneConfig,
    prune_tool_results,
    select_compaction_span,
    should_compact,
)
from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.models import Message


class FixedEstimator:
    def count_message(self, message: Message) -> int:
        return 1


def message(
    message_id: int, role: MessageRole, content: str, tool_call_id: str | None = None
) -> Message:
    return Message(
        id=message_id,
        session_id="s1",
        run_id="r1",
        role=role,
        content=content,
        tool_call_id=tool_call_id,
    )


def test_prune_head_tail_and_unicode() -> None:
    text = "你" * 30_000
    result = prune_tool_results(
        [message(1, MessageRole.TOOL, text, "call-1")],
        PruneConfig(threshold_chars=100, head_chars=10, tail_chars=10),
    )

    content = str(result.messages[0].content)
    assert result.pruned_count == 1
    assert "pruned" in content
    assert content.startswith("你" * 10) and content.endswith("你" * 10)
    assert result.messages[0].tool_call_id == "call-1"


def test_prune_leaves_short_messages() -> None:
    result = prune_tool_results([message(1, MessageRole.TOOL, "short", "c")], PruneConfig())
    assert result.pruned_count == 0 and result.messages[0].content == "short"


def test_selection_keeps_tail_units() -> None:
    messages = [
        message(1, MessageRole.USER, "old"),
        message(2, MessageRole.ASSISTANT, "a"),
        message(3, MessageRole.TOOL, "t", "c1"),
        message(4, MessageRole.USER, "current"),
    ]

    span = select_compaction_span(messages, retain_tokens=3, estimator=FixedEstimator())

    assert span is not None
    assert span.first_kept_message_id == 2
    assert [item.id for item in span.summarized] == [1]


def test_selection_requires_at_least_two_units() -> None:
    messages = [message(1, MessageRole.USER, "only")]
    assert select_compaction_span(messages, retain_tokens=10, estimator=FixedEstimator()) is None


def test_should_compact() -> None:
    assert should_compact(86, 100, 0.85) is True
    assert should_compact(85, 100, 0.85) is False


def test_selection_never_cuts_current_user() -> None:
    messages = [
        message(1, MessageRole.USER, "old"),
        message(2, MessageRole.ASSISTANT, "a"),
        message(3, MessageRole.TOOL, "t" * 10_000, "c1"),
        message(4, MessageRole.USER, "current"),
    ]

    span = select_compaction_span(messages, retain_tokens=1, estimator=FixedEstimator())

    assert span is not None
    assert span.first_kept_message_id == 4
    assert [item.id for item in span.summarized] == [1, 2, 3]
