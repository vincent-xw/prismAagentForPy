from datetime import timedelta

from pydantic import JsonValue

from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import ExecutionMode, MessageRole, RunStatus
from prism_agent_kit.core.models import Message, Run, ToolCall, utc_now
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def seed_waiting_remote_run(
    uow_factory: UnitOfWorkFactory,
    *,
    tool_name: str = "wait_for_host",
    tool_input: JsonValue = None,
    call_id: str = "call-1",
) -> tuple[Run, ToolCall]:
    """创建等待远端工具回填的 Run 和 ToolCall。"""
    effective_input: JsonValue = {"value": "one"} if tool_input is None else tool_input
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
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.USER,
                content="hello",
            )
        )
        await uow.commit()

    async with uow_factory() as uow:
        claimed = await uow.runs.claim_next()
        assert claimed is not None
        assistant = await uow.messages.append(
            Message(
                session_id=session.id,
                run_id=run.id,
                role=MessageRole.ASSISTANT,
                content="",
            )
        )
        assert assistant.id is not None
        call = await uow.tool_calls.create_many(
            [
                ToolCall(
                    id=call_id,
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name=tool_name,
                    execution_mode=ExecutionMode.REMOTE,
                    input=effective_input,
                    input_digest=canonical_json_digest(effective_input),
                    expires_at=utc_now() + timedelta(minutes=5),
                )
            ]
        )
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_TOOL)
        await uow.commit()
        return run, call[0]
