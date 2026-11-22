import json
from collections.abc import Sequence
from typing import Protocol

import tiktoken
from pydantic import JsonValue

from prism_agent_kit.core.models import Message

_MESSAGE_FRAMING_OVERHEAD_TOKENS = 4


class TokenEstimator(Protocol):
    """上下文预算使用的可替换 Token 估算端口。"""

    def count_text(self, text: str) -> int: ...

    def count_json(self, value: JsonValue) -> int: ...

    def count_message(self, message: Message) -> int: ...

    def count_messages(self, messages: Sequence[Message]) -> int: ...


class TiktokenEstimator:
    """基于显式 tiktoken encoding 的估算器。"""

    def __init__(self, encoding_name: str) -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count_text(self, text: str) -> int:
        """统计纯文本 token 数。"""
        return len(self._encoding.encode(text))

    def count_json(self, value: JsonValue) -> int:
        """把 JSON 值稳定序列化后统计 token 数。"""
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return self.count_text(serialized)

    def count_message(self, message: Message) -> int:
        """统计单条消息内容、角色与框架开销。"""
        if isinstance(message.content, str):
            content_tokens = self.count_text(message.content)
        elif message.content is None:
            content_tokens = 0
        else:
            content_tokens = self.count_json(message.content)

        reasoning_tokens = (
            self.count_text(message.reasoning) if message.reasoning is not None else 0
        )
        tool_call_tokens = (
            self.count_text(message.tool_call_id) if message.tool_call_id is not None else 0
        )
        return (
            _MESSAGE_FRAMING_OVERHEAD_TOKENS
            + self.count_text(message.role.value)
            + content_tokens
            + reasoning_tokens
            + tool_call_tokens
        )

    def count_messages(self, messages: Sequence[Message]) -> int:
        """统计一组消息的总 token 数。"""
        return sum(self.count_message(message) for message in messages)
