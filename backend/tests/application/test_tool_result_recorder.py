from tests.fakes import RecordingEventPublisher

from prism_agent_kit.application.tool_result_recorder import ToolResultRecorder
from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    MessageRole,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import ErrorCode
from prism_agent_kit.core.models import Message, Run, ToolCall
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolExecutionResult


async def seed_pending_call(uow_factory: UnitOfWorkFactory) -> tuple[str, str]:
    """创建 running Run 与一个 pending 本地工具调用。"""
    async with uow_factory() as uow:
        session = await uow.sessions.create()
        run = await uow.runs.create(
            Run(
                session_id=session.id,
                input_text="hello",
                prompt_name="default",
                prompt_version="1",
                system_prompt="system",
                model="test-model",
            )
        )
        await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.USER, content="hello")
        )
        await uow.commit()
    async with uow_factory() as uow:
        await uow.runs.claim_next()
        assistant = await uow.messages.append(
            Message(session_id=session.id, run_id=run.id, role=MessageRole.ASSISTANT, content="")
        )
        assert assistant.id is not None
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-1",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="file_write",
                    execution_mode=ExecutionMode.LOCAL,
                    input={"path": "a.md"},
                    input_digest=canonical_json_digest({"path": "a.md"}),
                )
            ]
        )
        await uow.tool_calls.start(run.id, "call-1")
        await uow.commit()
        return run.id, "call-1"


async def test_record_success_writes_message_and_event(uow_factory: UnitOfWorkFactory) -> None:
    run_id, call_id = await seed_pending_call(uow_factory)
    publisher = RecordingEventPublisher()
    recorder = ToolResultRecorder(uow_factory=uow_factory, event_publisher=publisher)

    await recorder.record(run_id, call_id, ToolExecutionResult.success({"ok": True}))

    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run_id, call_id)
        assert call.status is ToolCallStatus.SUCCEEDED
        assert call.output == {"ok": True}
        events = await uow.events.list_after(run_id, after_id=0)
        assert EventType.TOOL_COMPLETED in [event.event_type for event in events]
    assert [event.event_type for event in publisher.events] == [EventType.TOOL_COMPLETED]


async def test_record_failure_writes_error_content(uow_factory: UnitOfWorkFactory) -> None:
    run_id, call_id = await seed_pending_call(uow_factory)
    publisher = RecordingEventPublisher()
    recorder = ToolResultRecorder(uow_factory=uow_factory, event_publisher=publisher)

    await recorder.record(
        run_id,
        call_id,
        ToolExecutionResult.failure(ErrorCode.TOOL_EXECUTION_FAILED, "写入失败"),
    )

    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run_id, call_id)
        assert call.status is ToolCallStatus.FAILED
        assert call.error_code == ErrorCode.TOOL_EXECUTION_FAILED.value
        events = await uow.events.list_after(run_id, after_id=0)
        assert EventType.TOOL_FAILED in [event.event_type for event in events]
    run_status = None
    async with uow_factory() as uow:
        run = await uow.runs.get(run_id)
        run_status = run.status
    assert run_status is RunStatus.RUNNING
