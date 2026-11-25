def test_mcp_server_crud(api_client) -> None:
    created = api_client.post(
        "/api/v1/mcp/servers",
        json={"name": "demo", "transport": "stdio", "command": "python", "args": []},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "disabled"
    assert body["tool_count"] == 0
    assert body["env_keys"] == []

    listed = api_client.get("/api/v1/mcp/servers")
    assert listed.status_code == 200 and len(listed.json()) == 1

    patched = api_client.patch(
        f"/api/v1/mcp/servers/{body['id']}",
        json={"name": "demo", "transport": "stdio", "command": "python", "args": ["x.py"]},
    )
    assert patched.status_code == 200

    deleted = api_client.delete(f"/api/v1/mcp/servers/{body['id']}")
    assert deleted.status_code == 204
    assert api_client.get("/api/v1/mcp/servers").json() == []


def test_mcp_secret_rejected(api_client) -> None:
    response = api_client.post(
        "/api/v1/mcp/servers",
        json={
            "name": "x",
            "transport": "stdio",
            "command": "python",
            "env": {"API_KEY": "sk-abcdefghijklmnopqrstuvwxyz"},
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MCP_CONFIG_INVALID"


def test_mcp_enable_tools_disable(api_client) -> None:
    created = api_client.post(
        "/api/v1/mcp/servers",
        json={"name": "demo", "transport": "stdio", "command": "python"},
    ).json()

    enabled = api_client.post(f"/api/v1/mcp/servers/{created['id']}/enable")
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["status"] == "connected"
    assert enabled.json()["tool_count"] == 1

    tools = api_client.get(f"/api/v1/mcp/servers/{created['id']}/tools").json()
    assert tools["tools"][0]["name"] == "mcp__demo__echo"

    disabled = api_client.post(f"/api/v1/mcp/servers/{created['id']}/disable")
    assert disabled.json()["status"] == "disabled"


def test_mcp_missing_server_404(api_client) -> None:
    response = api_client.get("/api/v1/mcp/servers/missing/tools")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MCP_SERVER_NOT_FOUND"


def test_mcp_view_masks_literals_and_update_keeps_masked(api_client) -> None:
    created = api_client.post(
        "/api/v1/mcp/servers",
        json={
            "name": "demo",
            "transport": "stdio",
            "command": "python",
            "env": {"PLAIN": "value", "REF": "${TOKEN}"},
        },
    ).json()
    assert created["env"] == {"PLAIN": "***", "REF": "${TOKEN}"}

    patched = api_client.patch(
        f"/api/v1/mcp/servers/{created['id']}",
        json={
            "name": "demo",
            "transport": "stdio",
            "command": "python",
            "env": {"PLAIN": "***", "REF": "${TOKEN}"},
        },
    )
    assert patched.status_code == 200, patched.text


def test_mcp_view_returns_connection_fields(api_client) -> None:
    created = api_client.post(
        "/api/v1/mcp/servers",
        json={"name": "Demo", "transport": "http", "url": "https://mcp.example/mcp"},
    ).json()
    assert created["url"] == "https://mcp.example/mcp"
    assert created["command"] is None and created["args"] == []

    stdio = api_client.post(
        "/api/v1/mcp/servers",
        json={"name": "Local", "transport": "stdio", "command": "python", "args": ["a.py"]},
    ).json()
    assert stdio["command"] == "python" and stdio["args"] == ["a.py"] and stdio["url"] is None
