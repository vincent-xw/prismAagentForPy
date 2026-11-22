from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.models import Message, Run, RunEvent, Session, ToolCall
from prism_agent_kit.db.mappers import (
    message_to_domain,
    message_to_row,
    run_event_to_domain,
    run_event_to_row,
    run_to_domain,
    run_to_row,
    session_to_domain,
    session_to_row,
    tool_call_to_domain,
    tool_call_to_row,
)


def test_session_mapper_round_trips() -> None:
    session = Session(title="demo")

    assert session_to_domain(session_to_row(session)) == session


def test_run_mapper_round_trips() -> None:
    run = Run(
        session_id="session-1",
        input_text="你好",
        prompt_name="default",
        prompt_version="1",
        system_prompt="system",
        model="test-model",
        status=RunStatus.WAITING_FOR_TOOL,
        step_count=2,
    )

    assert run_to_domain(run_to_row(run)) == run


def test_message_mapper_round_trips() -> None:
    message = Message(
        session_id="session-1",
        run_id="run-1",
        role=MessageRole.ASSISTANT,
        content="完成",
        reasoning="先分析",
    )

    assert message_to_domain(message_to_row(message)) == message


def test_tool_call_mapper_round_trips() -> None:
    tool_call = ToolCall(
        id="call-1",
        run_id="run-1",
        assistant_message_id=1,
        tool_name="demo",
        execution_mode=ExecutionMode.REMOTE,
        status=ToolCallStatus.SUCCEEDED,
        input={"value": 1},
        output={"ok": True},
        input_digest="sha256:abc",
    )

    assert tool_call_to_domain(tool_call_to_row(tool_call)) == tool_call


def test_run_event_mapper_round_trips() -> None:
    event = RunEvent(
        run_id="run-1",
        event_type=EventType.TOOL_COMPLETED,
        payload={"call_id": "call-1"},
    )

    assert run_event_to_domain(run_event_to_row(event)) == event
