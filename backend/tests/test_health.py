from fastapi.testclient import TestClient

from prism_agent_kit import __version__


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "PrismAgentKit API"
    assert body["version"] == __version__
    assert body["environment"] == "test"
    assert body["workspace_fts"] in {"ok", "unsupported"}
