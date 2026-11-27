"""把一段历史压缩成结构化 checkpoint 摘要。"""

import asyncio
from dataclasses import dataclass

from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message
from prism_agent_kit.core.ports import ModelProvider, ModelRequest, TokenUsage

_SUMMARY_SYSTEM_PROMPT = (
    "You are now acting as a compaction engine for this AI coding assistant. "
    "Condense the conversation into a structured checkpoint that lets another model "
    "resume the work with no loss of essential context."
)
_SECTIONS = (
    "Primary Request and Intent",
    "Key Technical Concepts",
    "Files and Code",
    "Errors and Fixes",
    "Pending Jobs",
    "Current Work",
    "Next Step",
    "Critical Context",
)
_INSTRUCTIONS = "\n".join(
    [
        "Output EXACTLY the Markdown structure below: keep every section, in order.",
        'Use terse bullets, not prose paragraphs. Write "(none)" for an empty section.',
        "",
        *[f"## {section}" for section in _SECTIONS],
        "",
        "Rules: preserve exact file paths, commands, error strings, identifiers, numbers.",
        "Capture user feedback and corrections faithfully. Output only the checkpoint text.",
    ]
)
_TOOL_CHAR_LIMIT = 2_000


@dataclass(frozen=True)
class SummaryResult:
    """摘要文本与本次摘要请求的 token 用量。"""

    text: str
    usage: TokenUsage | None = None


async def summarize_span(
    provider: ModelProvider,
    messages: list[Message],
    *,
    previous_summary: str | None = None,
    max_output_tokens: int = 1_500,
    timeout_seconds: float = 30.0,
) -> SummaryResult:
    """调用模型生成 8 段摘要；空文本或 length 截断视为失败。"""
    conversation = _serialize(messages)
    if previous_summary:
        conversation = (
            f"<previous-summary>\n{previous_summary}\n</previous-summary>\n\n"
            f"The messages below are NEW conversation messages to incorporate:\n{conversation}"
        )
    request = ModelRequest(
        system_prompt=_SUMMARY_SYSTEM_PROMPT,
        messages=[
            Message(
                session_id="compaction",
                run_id="compaction",
                role=MessageRole.USER,
                content=f"{conversation}\n\n{_INSTRUCTIONS}",
            )
        ],
        max_output_tokens=max_output_tokens,
    )
    try:
        response = await asyncio.wait_for(provider.stream(request), timeout=timeout_seconds)
    except TimeoutError as error:
        raise AgentKitError(
            ErrorCode.COMPACTION_FAILED,
            "上下文摘要超时",
            http_status=504,
        ) from error
    text = response.text.strip()
    if not text or response.finish_reason == "length":
        raise AgentKitError(
            ErrorCode.COMPACTION_FAILED,
            "上下文摘要为空或被截断",
            http_status=502,
        )
    return SummaryResult(text=text, usage=response.usage)


def _serialize(messages: list[Message]) -> str:
    lines: list[str] = []
    for message in messages:
        text = message.content if isinstance(message.content, str) else str(message.content)
        if message.role is MessageRole.TOOL:
            text = text[:_TOOL_CHAR_LIMIT]
        lines.append(f"{message.role.value}: {text}")
    return "\n\n".join(lines)
