import httpx


def test_health_contract(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) >= {"status", "service", "version", "environment", "workspace_fts"}
    assert body["environment"] in {"development", "test", "production"}


def test_health_needs_no_auth(base_url):
    response = httpx.get(f"{base_url}/api/v1/health", timeout=10.0)
    assert response.status_code == 200
