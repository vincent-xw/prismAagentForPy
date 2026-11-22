from prism_agent_kit.core.enums import (
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run, RunEvent, Session, ToolCall


def test_run_status_serializes_as_string() -> None:
    assert RunStatus.WAITING_FOR_TOOL.value == "waiting_for_tool"
    assert RunStatus.QUEUED.value == "queued"


def test_domain_models_expose_expected_defaults() -> None:
    session = Session(title="demo")
    run = Run(
        session_id=session.id,
        input_text="你好",
        prompt_name="default",
        prompt_version="1",
        system_prompt="system",
        model="test-model",
    )
    message = Message(
        session_id=session.id,
        run_id=run.id,
        role=MessageRole.USER,
        content="你好",
    )
    tool_call = ToolCall(
        id="call-1",
        run_id=run.id,
        assistant_message_id=1,
        tool_name="demo",
        execution_mode=ExecutionMode.LOCAL,
        input={"value": 1},
        input_digest="sha256:abc",
    )
    event = RunEvent(run_id=run.id, event_type="run.queued", payload={})

    assert run.status is RunStatus.QUEUED
    assert run.step_count == 0
    assert run.prompt_ref == "default@1"
    assert message.id is None
    assert tool_call.status is ToolCallStatus.PENDING
    assert event.id is None
    assert session.updated_at.tzinfo is not None


def test_agent_kit_error_carries_stable_code_and_details() -> None:
    error = AgentKitError(
        ErrorCode.INVALID_RUN_TRANSITION,
        "状态不允许",
        http_status=409,
        details={"target": "queued"},
    )

    assert str(error) == "状态不允许"
    assert error.code is ErrorCode.INVALID_RUN_TRANSITION
    assert error.http_status == 409
    assert error.details == {"target": "queued"}
