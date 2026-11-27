"""MCP 配置 v1.5 契约：明文入库、*** 掩码、错误码。"""

import uuid

import httpx


def _name() -> str:
    return f"mcp-{uuid.uuid4().hex[:8]}"


def _payload(name: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": name,
        "transport": "http",
        "url": "https://mcp.example.com/mcp",
        "headers": {"Authorization": "Bearer sk-contract"},
    }
    body.update(overrides)
    return body


def _create(client: httpx.Client, name: str, **overrides: object) -> dict:
    response = client.post("/api/v1/mcp/servers", json=_payload(name, **overrides))
    assert response.status_code == 200, response.text
    return response.json()


def test_plaintext_secret_is_masked(client):
    name = _name()
    created = _create(client, name)
    try:
        assert created["headers"] == {"Authorization": "***"}
        assert created["header_keys"] == ["Authorization"]
        assert "sk-contract" not in str(client.get("/api/v1/mcp/servers").json())
    finally:
        client.delete(f"/api/v1/mcp/servers/{created['id']}")


def test_masked_patch_keeps_secret(client):
    name = _name()
    created = _create(client, name)
    try:
        patched = client.patch(f"/api/v1/mcp/servers/{created['id']}", json=_payload(name))
        assert patched.status_code == 200, patched.text
        assert patched.json()["headers"] == {"Authorization": "***"}
    finally:
        client.delete(f"/api/v1/mcp/servers/{created['id']}")


def test_invalid_transport_is_400(client):
    response = client.post("/api/v1/mcp/servers", json={"name": _name(), "transport": "grpc"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_name_is_400(client):
    name = _name()
    created = _create(client, name)
    try:
        duplicate = client.post("/api/v1/mcp/servers", json=_payload(name))
        assert duplicate.status_code == 400, duplicate.text
        assert duplicate.json()["error"]["code"] == "MCP_CONFIG_INVALID"
    finally:
        client.delete(f"/api/v1/mcp/servers/{created['id']}")


def test_tools_empty_for_disabled_server(client):
    name = _name()
    created = _create(client, name)
    try:
        tools = client.get(f"/api/v1/mcp/servers/{created['id']}/tools")
        assert tools.status_code == 200, tools.text
        assert tools.json()["server_id"] == created["id"]
        assert tools.json()["tools"] == []
    finally:
        client.delete(f"/api/v1/mcp/servers/{created['id']}")
