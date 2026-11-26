import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from prism_agent_kit.application.container import ApplicationContainer
from prism_agent_kit.core.ports import ModelResponse
from prism_agent_kit.main import create_app
from tests.fakes import ScriptedModelProvider
from tests.support.skill_helpers import make_skill
from tests.test_agent_e2e import make_settings, wait_for_run_status


def test_e2e_skill_context_once_and_catalog(tmp_path: Path, migrated_database_path: Path) -> None:
    skills_root = tmp_path / "skills"
    make_skill(skills_root, "pdf-tools", "Extract PDFs.", "# PDF TOOLS BODY")
    provider = ScriptedModelProvider(
        [ModelResponse(text="done", reasoning=None), ModelResponse(text="again", reasoning=None)]
    )
    settings = make_settings(
        migrated_database_path,
        api_token=None,
        skills_paths=str(skills_root),
    )
    container = ApplicationContainer(settings, model_provider=provider)
    application = create_app(settings, container_factory=lambda _: container)

    with TestClient(application) as client:
        session = client.post("/api/v1/sessions", json={"title": "demo"}).json()

        first = client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "整理 PDF", "skill_name": "pdf-tools"},
        )
        assert first.status_code == 202, first.text
        wait_for_run_status(client, first.json()["id"], {"succeeded"})

        messages = client.get(f"/api/v1/sessions/{session['id']}/messages").json()["items"]
        assert any(
            "PDF TOOLS BODY" in str(message.content) for message in provider.requests[0].messages
        )
        kinds = [item["kind"] for item in messages]
        assert kinds.count("skill_context") == 1
        skill_content = next(
            item["content"] for item in messages if item["kind"] == "skill_context"
        )
        assert "PDF TOOLS BODY" in str(skill_content)

        second = client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "再来一次"},
        )
        assert second.status_code == 202, second.text
        wait_for_run_status(client, second.json()["id"], {"succeeded"})

        messages = client.get(f"/api/v1/sessions/{session['id']}/messages").json()["items"]
        assert [item["kind"] for item in messages].count("skill_context") == 1

    with sqlite3.connect(migrated_database_path) as connection:
        rows = connection.execute("SELECT system_prompt FROM runs ORDER BY created_at").fetchall()
    assert "<available_skills>" in rows[0][0]
    assert "PDF TOOLS BODY" not in rows[1][0]
