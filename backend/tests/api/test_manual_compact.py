from prism_agent_kit.core.enums import MessageRole, RunStatus
from prism_agent_kit.core.models import Message, Run
from prism_agent_kit.db.uow import UnitOfWorkFactory


def profile_payload() -> dict[str, object]:
    return {
        "name": "p1",
        "base_url": "https://api.example.com/v1",
        "model": "m1",
        "api_key_env": "OPENAI_API_KEY",
        "context_window": 128000,
        "max_output_tokens": 4096,
    }


async def test_manual_compact_creates_checkpoint(
    api_client, uow_factory: UnitOfWorkFactory
) -> None:
    profile = api_client.post("/api/v1/model-profiles", json=profile_payload()).json()
    api_client.post(f"/api/v1/model-profiles/{profile['id']}/activate")
    session = api_client.post("/api/v1/sessions", json={"title": "demo"}).json()

    async with uow_factory() as uow:
        run = await uow.runs.create(
            Run(
                session_id=session["id"],
                status=RunStatus.SUCCEEDED,
                input_text="q",
                prompt_name="default",
                prompt_version="1",
                system_prompt="s",
                model="m1",
            )
        )
        for role, content in [
            (MessageRole.USER, "old question"),
            (MessageRole.ASSISTANT, "old answer"),
            (MessageRole.USER, "new question"),
        ]:
            await uow.messages.append(
                Message(session_id=session["id"], role=role, content=content, run_id=run.id)
            )
        await uow.commit()

    response = api_client.post(f"/api/v1/sessions/{session['id']}/compact")

    assert response.status_code == 200, response.text
    assert response.json()["compacted"] is True
    assert response.json()["tokens_after"] < response.json()["tokens_before"]
