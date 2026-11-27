import json

import httpx


def _create_session(client: httpx.Client) -> str:
    return client.post("/api/v1/sessions", json={"title": "contract"}).json()["id"]


def _stream(client: httpx.Client, run_id: str) -> list[dict]:
    frames: list[dict] = []
    with client.stream("GET", f"/api/v1/runs/{run_id}/events", timeout=30.0) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        event = None
        event_id = None
        for line in response.iter_lines():
            if not line:
                if event is not None:
                    frames.append({"event": event, "id": event_id})
                event, event_id = None, None
                continue
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("id:"):
                event_id = line[3:].strip()
    return frames


def test_run_lifecycle_streams_events(client):
    session_id = _create_session(client)
    created = client.post(f"/api/v1/sessions/{session_id}/runs", json={"input": "你好"})
    assert created.status_code == 202
    run = created.json()
    assert run["status"] in {"queued", "running", "waiting_for_tool", "succeeded"}

    frames = _stream(client, run["id"])
    names = [frame["event"] for frame in frames]

    assert names[0] == "run.queued"
    assert names[-1] == "run.succeeded", names
    persisted = [frame for frame in frames if frame["id"] is not None]
    assert [int(frame["id"]) for frame in persisted] == list(range(1, len(persisted) + 1))
