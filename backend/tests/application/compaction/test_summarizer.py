import pytest
from tests.fakes import ScriptedModelProvider

from prism_agent_kit.application.compaction.summarizer import summarize_span
from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message
from prism_agent_kit.core.ports import ModelResponse, TokenUsage

SUMMARY = """## Primary Request and Intent
- fix bug

## Key Technical Concepts
- python

## Files and Code
- a.py

## Errors and Fixes
- boom

## Pending Jobs
- (none)

## Current Work
- testing

## Next Step
- run tests

## Critical Context
- keep paths
"""


def make_message(message_id: int, role: MessageRole, content: str) -> Message:
    return Message(id=message_id, session_id="s1", run_id="r1", role=role, content=content)


async def test_summary_has_eight_sections_and_usage() -> None:
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                text=SUMMARY,
                reasoning=None,
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )
        ]
    )

    result = await summarize_span(
        provider,
        [make_message(1, MessageRole.USER, "hi"), make_message(2, MessageRole.TOOL, "x" * 3000)],
    )

    assert "## Primary Request and Intent" in result.text
    assert "## Critical Context" in result.text
    assert result.usage is not None and result.usage.total_tokens == 30
    assert "x" * 2001 not in provider.requests[0].messages[0].content  # type: ignore[union-attr]


async def test_length_finish_rejected() -> None:
    provider = ScriptedModelProvider(
        [ModelResponse(text=SUMMARY, reasoning=None, finish_reason="length")]
    )

    with pytest.raises(AgentKitError) as error:
        await summarize_span(provider, [make_message(1, MessageRole.USER, "hi")])
    assert error.value.code is ErrorCode.COMPACTION_FAILED


async def test_previous_summary_included() -> None:
    provider = ScriptedModelProvider([ModelResponse(text=SUMMARY, reasoning=None)])

    await summarize_span(
        provider,
        [make_message(1, MessageRole.USER, "hi")],
        previous_summary="OLD FACTS",
    )

    assert "OLD FACTS" in provider.requests[0].messages[0].content  # type: ignore[union-attr]
