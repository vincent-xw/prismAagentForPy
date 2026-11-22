import pytest

from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import ExecutionMode, MessageRole, ToolCallStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run, ToolCall
from prism_agent_kit.db.repositories.tool_calls import CompleteToolResult
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def seed_tool_calls(
    uow_factory: UnitOfWorkFactory,
    count: int = 1,
) -> tuple[str, list[str]]:
    """创建一个 Run 以及指定数量的待执行工具调用。"""
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
        assistant = await uow.messages.append(
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.ASSISTANT,
                content=None,
            )
        )
        assert assistant.id is not None
        calls = [
            ToolCall(
                id=f"call-{index}",
                run_id=run.id,
                assistant_message_id=assistant.id,
                tool_name="demo",
                execution_mode=ExecutionMode.LOCAL,
                input={"index": index},
                input_digest=canonical_json_digest({"index": index}),
            )
            for index in range(count)
        ]
        await uow.tool_calls.create_many(calls)
        await uow.commit()
        return run.id, [call.id for call in calls]


async def test_first_completion_commits_history_and_event(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run_id, call_ids = await seed_tool_calls(uow_factory)

    async with uow_factory() as uow:
        result = await uow.tool_calls.complete(
            run_id,
            call_ids[0],
            {"ok": True},
        )
        await uow.commit()

    assert result is CompleteToolResult.COMMITTED

    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run_id, call_ids[0])
        messages = await uow.events.list_after(run_id)

    assert call.status is ToolCallStatus.SUCCEEDED
    assert call.output == {"ok": True}
    assert len(messages) == 1
    assert messages[0].event_type.value == "tool.completed"


async def test_complete_tool_result_is_idempotent(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run_id, call_ids = await seed_tool_calls(uow_factory)

    async with uow_factory() as uow:
        first = await uow.tool_calls.complete(run_id, call_ids[0], {"ok": True})
        await uow.commit()

    async with uow_factory() as uow:
        second = await uow.tool_calls.complete(run_id, call_ids[0], {"ok": True})
        await uow.commit()

    assert first is CompleteToolResult.COMMITTED
    assert second is CompleteToolResult.ALREADY_COMMITTED

    async with uow_factory() as uow:
        events = await uow.events.list_after(run_id)

    assert len(events) == 1


async def test_conflicting_tool_result_does_not_modify_history(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run_id, call_ids = await seed_tool_calls(uow_factory)

    async with uow_factory() as uow:
        await uow.tool_calls.complete(run_id, call_ids[0], {"ok": True})
        await uow.commit()

    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as error:
            await uow.tool_calls.complete(run_id, call_ids[0], {"ok": False})
        run = await uow.runs.get(run_id)
        messages = await uow.messages.list_for_session(run.session_id)

    assert error.value.code is ErrorCode.TOOL_RESULT_CONFLICT
    assert error.value.http_status == 409
    assert len([message for message in messages if message.role is MessageRole.TOOL]) == 1


async def test_close_open_calls_adds_tool_messages_for_every_call(
    uow_factory: UnitOfWorkFactory,
) -> None:
    run_id, _ = await seed_tool_calls(uow_factory, count=2)

    async with uow_factory() as uow:
        closed = await uow.tool_calls.close_open_calls(
            run_id,
            ErrorCode.TOOL_EXECUTION_FAILED,
            "工具执行失败",
        )
        await uow.commit()

    assert len(closed) == 2

    async with uow_factory() as uow:
        calls = await uow.tool_calls.list_for_run(run_id)
        events = await uow.events.list_after(run_id)

    assert all(call.status is ToolCallStatus.FAILED for call in calls)
    assert len(events) == 2
