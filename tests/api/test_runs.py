from fastapi.testclient import TestClient


def test_blank_run_input_is_rejected(api_client: TestClient) -> None:
    session = api_client.post("/api/v1/sessions", json={}).json()

    response = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_missing_session_returns_not_found(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/sessions/missing/runs",
        json={"input": "hello"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
