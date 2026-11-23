from fastapi.testclient import TestClient


def test_create_list_and_get_sessions(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/sessions", json={"title": "demo"})

    assert created.status_code == 201
    session = created.json()
    assert session["title"] == "demo"

    listed = api_client.get("/api/v1/sessions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [session["id"]]

    loaded = api_client.get(f"/api/v1/sessions/{session['id']}")
    assert loaded.status_code == 200
    assert loaded.json() == session


def test_create_run_persists_user_message(api_client: TestClient) -> None:
    session = api_client.post("/api/v1/sessions", json={"title": "demo"}).json()

    response = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={
            "input": "hello",
            "prompt_ref": "default@1",
            "metadata": {"client": "test"},
        },
    )

    assert response.status_code == 202
    run = response.json()
    assert run["session_id"] == session["id"]
    assert run["status"] == "queued"

    messages = api_client.get(f"/api/v1/sessions/{session['id']}/messages").json()
    assert [item["role"] for item in messages["items"]] == ["user"]
    assert messages["items"][0]["content"] == "hello"

    loaded = api_client.get(f"/api/v1/runs/{run['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["status"] == "queued"


def test_second_active_run_is_rejected(api_client: TestClient) -> None:
    session = api_client.post("/api/v1/sessions", json={}).json()
    first = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "first"},
    )
    second = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "second"},
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RUN_CONFLICT"


def test_unknown_prompt_version_is_rejected(api_client: TestClient) -> None:
    session = api_client.post("/api/v1/sessions", json={}).json()

    response = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "hello", "prompt_ref": "missing@1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROMPT_NOT_FOUND"


def test_bind_workspace_to_existing_session(api_client, tmp_path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace_id = api_client.post("/api/v1/workspaces", json={"path": str(root)}).json()["id"]
    session = api_client.post("/api/v1/sessions", json={"title": "demo"}).json()

    response = api_client.post(
        f"/api/v1/sessions/{session['id']}/workspace",
        json={"workspace_id": workspace_id},
    )

    assert response.status_code == 200
    assert response.json()["workspace_id"] == workspace_id


def test_bind_unknown_workspace_returns_404(api_client) -> None:
    session = api_client.post("/api/v1/sessions", json={"title": "demo"}).json()
    response = api_client.post(
        f"/api/v1/sessions/{session['id']}/workspace",
        json={"workspace_id": "missing"},
    )
    assert response.status_code == 404
