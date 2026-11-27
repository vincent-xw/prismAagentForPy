from prism_agent_kit.core.enums import ExecutionMode, MessageRole, RunStatus, ToolCallStatus
from prism_agent_kit.core.models import Message, Run, ToolCall
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def test_legacy_run_synthesizes_step(api_client, uow_factory: UnitOfWorkFactory) -> None:
    session = api_client.post("/api/v1/sessions", json={"title": "demo"}).json()
    async with uow_factory() as uow:
        run = await uow.runs.create(
            Run(
                session_id=session["id"],
                status=RunStatus.SUCCEEDED,
                input_text="hi",
                prompt_name="default",
                prompt_version="1",
                system_prompt="s",
                model="m1",
            )
        )
        assistant = await uow.messages.append(
            Message(
                session_id=session["id"],
                run_id=run.id,
                role=MessageRole.ASSISTANT,
                content="using echo",
            )
        )
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="tc1",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="echo",
                    execution_mode=ExecutionMode.LOCAL,
                    status=ToolCallStatus.SUCCEEDED,
                    input={"text": "x"},
                    output={"text": "x"},
                    input_digest="digest",
                )
            ]
        )
        await uow.commit()

    data = api_client.get(f"/api/v1/sessions/{session['id']}/trajectory").json()

    turn = data["turns"][0]
    step = turn["steps"][0]
    assert step["legacy"] is True
    assert step["usage"] is None
    assert step["tools"][0]["tool_name"] == "echo"
