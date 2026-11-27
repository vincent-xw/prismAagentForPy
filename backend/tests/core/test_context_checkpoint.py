from prism_agent_kit.core.compaction import checkpoint_message
from prism_agent_kit.core.context import ContextAssembler
from prism_agent_kit.core.enums import MessageKind, MessageRole
from prism_agent_kit.core.models import Message


class _Estimator:
    def count_text(self, text: str) -> int:
        return 1

    def count_json(self, value: object) -> int:
        return 1

    def count_message(self, message: Message) -> int:
        return 1

    def count_tool_call(self, tool_call: object) -> int:
        return 1


def user(message_id: int, content: str) -> Message:
    return Message(
        id=message_id, session_id="s1", run_id="r1", role=MessageRole.USER, content=content
    )


def test_checkpoint_never_trimmed() -> None:
    assembler = ContextAssembler(
        _Estimator(), context_window=10, max_output_tokens=1, safety_margin_tokens=1
    )
    messages = [
        checkpoint_message(session_id="s1", run_id="r1", summary="x" * 500),
        user(1, "old"),
        user(2, "current"),
    ]

    assembly = assembler.assemble(system_prompt="s", messages=messages)

    assert assembly.messages[0].kind is MessageKind.CHECKPOINT
    assert any(message.content == "current" for message in assembly.messages)
