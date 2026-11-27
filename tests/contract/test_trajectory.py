"""轨迹与手动压缩的跨语言契约。"""

import httpx


def _session(client: httpx.Client) -> str:
    response = client.post("/api/v1/sessions", json={"title": "contract-traj"})
    assert response.status_code in {200, 201}, response.text
    return response.json()["id"]


def test_empty_session_has_empty_trajectory(client):
    session_id = _session(client)

    response = client.get(f"/api/v1/sessions/{session_id}/trajectory")

    assert response.status_code == 200, response.text
    assert response.json()["turns"] == []


def test_trajectory_reports_turn_for_run(client):
    session_id = _session(client)
    run = client.post(f"/api/v1/sessions/{session_id}/runs", json={"input": "你好"})
    assert run.status_code == 202, run.text

    response = client.get(f"/api/v1/sessions/{session_id}/trajectory")

    assert response.status_code == 200, response.text
    turns = response.json()["turns"]
    assert len(turns) == 1
    assert turns[0]["run"]["id"] == run.json()["id"]
    assert isinstance(turns[0]["steps"], list)
    assert isinstance(turns[0]["compactions"], list)


def test_trajectory_limit_validation(client):
    session_id = _session(client)

    response = client.get(f"/api/v1/sessions/{session_id}/trajectory?limit=0")

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
