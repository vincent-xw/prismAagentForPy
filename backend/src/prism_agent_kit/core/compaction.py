"""上下文压缩的纯函数：确定性裁剪、预算判定与选段。"""

from dataclasses import dataclass, field
from typing import Protocol

from prism_agent_kit.core.enums import MessageKind, MessageRole
from prism_agent_kit.core.models import Message

_PRUNE_MARKER_TEMPLATE = "\n…(pruned {removed} chars)…\n"


class EstimatorLike(Protocol):
    def count_message(self, message: Message) -> int: ...


@dataclass(frozen=True)
class PruneConfig:
    """tool 结果裁阈值与保留头尾字符数。"""

    threshold_chars: int = 8_000
    head_chars: int = 2_000
    tail_chars: int = 2_000


@dataclass(frozen=True)
class PruneResult:
    """裁剪后的发送副本与统计。"""

    messages: list[Message]
    pruned_chars: int = 0
    pruned_count: int = 0


@dataclass(frozen=True)
class CompactionSpan:
    """一次压缩要摘要的区间与保留起点。"""

    summarized: list[Message] = field(default_factory=list)
    first_kept_message_id: int = 0
    tokens: int = 0


def prune_tool_results(messages: list[Message], config: PruneConfig) -> PruneResult:
    """只缩短 tool 消息的文本内容，不改角色/配对/数据库。"""
    pruned: list[Message] = []
    pruned_chars = 0
    pruned_count = 0
    for message in messages:
        if message.role is not MessageRole.TOOL:
            pruned.append(message)
            continue
        text = message.content if isinstance(message.content, str) else str(message.content)
        if len(text) <= config.threshold_chars:
            pruned.append(message)
            continue
        kept_head = text[: config.head_chars]
        kept_tail = text[-config.tail_chars :] if config.tail_chars > 0 else ""
        removed = len(text) - len(kept_head) - len(kept_tail)
        marker = _PRUNE_MARKER_TEMPLATE.format(removed=removed)
        pruned.append(message.model_copy(update={"content": kept_head + marker + kept_tail}))
        pruned_chars += removed
        pruned_count += 1
    return PruneResult(messages=pruned, pruned_chars=pruned_chars, pruned_count=pruned_count)


def should_compact(estimated_tokens: int, input_budget: int, ratio: float) -> bool:
    """估算 token 是否超过预算的触发比例。"""
    return input_budget > 0 and estimated_tokens > input_budget * ratio


def select_compaction_span(
    messages: list[Message],
    *,
    retain_tokens: int,
    estimator: EstimatorLike,
) -> CompactionSpan | None:
    """从最旧开始选一段摘要，保留尾部约 retain_tokens；不切断 assistant/tool 配对。"""
    units = _units(messages)
    if len(units) < 2:
        return None
    retained = 0
    cut = len(messages)
    for start, end in reversed(units):
        unit_tokens = sum(estimator.count_message(message) for message in messages[start:end])
        if retained + unit_tokens > retain_tokens and cut < len(messages):
            break
        retained += unit_tokens
        cut = start
    last_user = max(
        (index for index, message in enumerate(messages) if message.role is MessageRole.USER),
        default=-1,
    )
    cut = min(cut, last_user)
    if cut <= 0 or cut >= len(messages):
        return None
    first_kept = messages[cut]
    if first_kept.id is None:
        return None
    summarized = messages[:cut]
    return CompactionSpan(
        summarized=summarized,
        first_kept_message_id=first_kept.id,
        tokens=sum(estimator.count_message(message) for message in summarized),
    )


def _units(messages: list[Message]) -> list[tuple[int, int]]:
    """按 assistant + 后续 tool 分组；user 单独成组。"""
    units: list[tuple[int, int]] = []
    index = 0
    while index < len(messages):
        start = index
        if messages[index].role is MessageRole.USER:
            index += 1
        else:
            index += 1
            while index < len(messages) and messages[index].role is MessageRole.TOOL:
                index += 1
        units.append((start, index))
    return units


def checkpoint_message(*, session_id: str, run_id: str, summary: str) -> Message:
    """构造不入库的 checkpoint 合成消息，供组装时置于最前。"""
    return Message(
        id=None,
        session_id=session_id,
        run_id=run_id,
        role=MessageRole.USER,
        kind=MessageKind.CHECKPOINT,
        content=f"<conversation_checkpoint>\n{summary}\n</conversation_checkpoint>",
    )


@dataclass(frozen=True)
class CompactionConfig:
    """引擎内的压缩策略配置。"""

    enabled: bool = True
    threshold_ratio: float = 0.85
    retain_ratio: float = 0.2
    retain_tokens: int = 20_000
    prune: PruneConfig = field(default_factory=PruneConfig)
    timeout_seconds: float = 30.0
    max_summary_output_tokens: int = 1_500
