from pathlib import Path

from fastapi.testclient import TestClient


def test_workspace_crud_and_tree(api_client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("工作区检索", encoding="utf-8")

    created = api_client.post("/api/v1/workspaces", json={"path": str(root)})
    assert created.status_code == 200
    body = created.json()
    assert body["is_active"] is True
    workspace_id = body["id"]

    listed = api_client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    assert listed.json()["active_id"] == workspace_id

    tree = api_client.get(f"/api/v1/workspaces/{workspace_id}/tree", params={"path": "."})
    assert tree.status_code == 200
    assert [item["name"] for item in tree.json()["items"]] == ["docs"]

    file_response = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/file",
        params={"path": "docs/a.md"},
    )
    assert file_response.status_code == 200
    assert file_response.json()["content"] == "工作区检索"

    rejected = api_client.post("/api/v1/workspaces", json={"path": "relative"})
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "WORKSPACE_PATH_INVALID"


def test_workspace_escape_rejected(api_client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    workspace_id = api_client.post("/api/v1/workspaces", json={"path": str(root)}).json()["id"]

    response = api_client.get(
        f"/api/v1/workspaces/{workspace_id}/file",
        params={"path": "../secret.txt"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WORKSPACE_PATH_OUTSIDE"


def test_health_reports_workspace_fts(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/health").json()["workspace_fts"] == "ok"
