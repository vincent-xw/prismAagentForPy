"""工作区 v1.3 契约：命名后缀、权限档位、会话绑定与目录树。"""

import uuid

import httpx


def _name() -> str:
    return f"contract-{uuid.uuid4().hex[:8]}"


def _create(client: httpx.Client, name: str, **extra: object) -> dict:
    response = client.post("/api/v1/workspaces", json={"name": name, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def _delete(client: httpx.Client, workspace_id: str) -> None:
    client.delete(f"/api/v1/workspaces/{workspace_id}")


def test_named_workspace_defaults_and_suffix(client):
    name = _name()
    first = _create(client, name)
    second = _create(client, name)
    try:
        assert first["permission_mode"] == "workspace_write"
        assert first["name"] == name
        assert second["root_path"] != first["root_path"]
        assert second["root_path"].endswith(f"{name}-2")
    finally:
        _delete(client, second["id"])
        _delete(client, first["id"])


def test_patch_permission_mode_and_validation(client):
    workspace = _create(client, _name())
    try:
        patched = client.patch(
            f"/api/v1/workspaces/{workspace['id']}", json={"permission_mode": "read_only"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["permission_mode"] == "read_only"

        invalid = client.patch(
            f"/api/v1/workspaces/{workspace['id']}", json={"permission_mode": "root"}
        )
        assert invalid.status_code == 422, invalid.text
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        _delete(client, workspace["id"])


def test_bind_workspace_to_session_and_tree(client):
    workspace = _create(client, _name())
    try:
        session = client.post("/api/v1/sessions", json={"title": "ws-contract"})
        assert session.status_code in {200, 201}, session.text
        session_id = session.json()["id"]

        bound = client.post(
            f"/api/v1/sessions/{session_id}/workspace", json={"workspace_id": workspace["id"]}
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["workspace_id"] == workspace["id"]

        tree = client.get(f"/api/v1/workspaces/{workspace['id']}/tree")
        assert tree.status_code == 200, tree.text
        assert isinstance(tree.json()["items"], list)
    finally:
        _delete(client, workspace["id"])
