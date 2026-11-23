from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import ExecutionMode, MessageRole, RunStatus
from prism_agent_kit.core.models import Message, Run, ToolCall, utc_now
from prism_agent_kit.core.workspace import Workspace
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def seed_waiting_approval(uow_factory: UnitOfWorkFactory, root: Path) -> dict[str, str]:
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(root)))
        session = await uow.sessions.create()
        run = await uow.runs.create(
            Run(
                session_id=session.id,
                input_text="hello",
                prompt_name="default",
                prompt_version="1",
                system_prompt="system",
                model="test-model",
                workspace_id=workspace.id,
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
        payload = {"path": "notes.md", "content": "hello", "mode": "overwrite"}
        await uow.tool_calls.create_many(
            [
                ToolCall(
                    id="call-write",
                    run_id=run.id,
                    assistant_message_id=assistant.id,
                    tool_name="file_write",
                    execution_mode=ExecutionMode.LOCAL,
                    input=payload,
                    input_digest=canonical_json_digest(payload),
                )
            ]
        )
        await uow.tool_calls.await_call(run.id, "call-write", utc_now() + timedelta(seconds=600))
        await uow.runs.transition(run.id, RunStatus.WAITING_FOR_APPROVAL)
        await uow.commit()
        return {"run_id": run.id, "call_id": "call-write"}


@pytest.mark.anyio
async def test_approval_endpoint_returns_call_and_run(api_env, tmp_path: Path) -> None:
    client, uow_factory = api_env
    if isinstance(client, TestClient):
        # TestClient 是同步的，用其 portal 执行异步造数
        seeded = client.portal.call(seed_waiting_approval, uow_factory, tmp_path)
    else:
        seeded = await seed_waiting_approval(uow_factory, tmp_path)

    response = client.post(
        f"/api/v1/runs/{seeded['run_id']}/tool-calls/{seeded['call_id']}/approval",
        json={"decision": "approve"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call"]["status"] == "succeeded"
    assert body["run"]["status"] == "queued"
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "hello"


@pytest.mark.anyio
async def test_preview_endpoint(api_env, tmp_path: Path) -> None:
    client, uow_factory = api_env
    (tmp_path / "notes.md").write_text("old", encoding="utf-8")
    if isinstance(client, TestClient):
        seeded = client.portal.call(seed_waiting_approval, uow_factory, tmp_path)
    else:
        seeded = await seed_waiting_approval(uow_factory, tmp_path)

    response = client.get(f"/api/v1/runs/{seeded['run_id']}/tool-calls/{seeded['call_id']}/preview")

    assert response.status_code == 200
    assert response.json()["exists"] is True
    assert response.json()["diff"] is not None
