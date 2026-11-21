from fastapi.testclient import TestClient

from prism_agent_kit import __version__


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "PrismAgentKit API",
        "version": __version__,
        "environment": "development",
    }
