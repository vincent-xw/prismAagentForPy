import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from prism_agent_kit.application.container import ApplicationContainer
from prism_agent_kit.core.ports import ModelResponse
from prism_agent_kit.main import create_app
from tests.fakes import ScriptedModelProvider
from tests.test_agent_e2e import make_settings, wait_for_run_status

SUMMARY = """## Primary Request and Intent
- demo

## Key Technical Concepts
- python

## Files and Code
- (none)

## Errors and Fixes
- (none)

## Pending Jobs
- (none)

## Current Work
- chat

## Next Step
- reply

## Critical Context
- keep going
"""


def test_e2e_compaction_checkpoint_and_trajectory(
    tmp_path: Path, migrated_database_path: Path
) -> None:
    provider = ScriptedModelProvider(
        [
            ModelResponse(text="first answer", reasoning=None),
            ModelResponse(text=SUMMARY, reasoning=None),
            ModelResponse(text="second answer", reasoning=None),
        ]
    )
    settings = make_settings(
        migrated_database_path,
        compaction_threshold_ratio=0.01,
        compaction_retain_tokens=1,
        compaction_retain_ratio=0.0,
    )
    container = ApplicationContainer(settings, model_provider=provider)
    application = create_app(settings, container_factory=lambda _: container)

    with TestClient(application) as client:
        session = client.post("/api/v1/sessions", json={"title": "demo"}).json()
        first = client.post(f"/api/v1/sessions/{session['id']}/runs", json={"input": "hello"})
        assert first.status_code == 202, first.text
        wait_for_run_status(client, first.json()["id"], {"succeeded"})

        second = client.post(f"/api/v1/sessions/{session['id']}/runs", json={"input": "again"})
        assert second.status_code == 202, second.text
        wait_for_run_status(client, second.json()["id"], {"succeeded"})

        trajectory = client.get(f"/api/v1/sessions/{session['id']}/trajectory").json()

    assert any(
        "conversation_checkpoint" in str(message.content)
        for message in provider.requests[2].messages
    )
    assert trajectory["turns"][1]["compactions"]
    with sqlite3.connect(migrated_database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM compaction_checkpoints").fetchone()[0]
        original = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 1
    assert original >= 4
