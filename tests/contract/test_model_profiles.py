"""模型档案 v1.2 契约：api_key 只写，响应只给 has_key。"""

import uuid

import httpx


def _payload(name: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": name,
        "base_url": "https://api.example.com/v1",
        "model": "contract-model",
        "api_key_env": "PRISM_CONTRACT_UNSET_KEY",
        "context_window": 128000,
        "max_output_tokens": 8192,
    }
    body.update(overrides)
    return body


def _create(client: httpx.Client, name: str, **overrides: object) -> dict:
    response = client.post("/api/v1/model-profiles", json=_payload(name, **overrides))
    assert response.status_code == 200, response.text
    return response.json()


def _delete(client: httpx.Client, profile_id: str) -> None:
    client.delete(f"/api/v1/model-profiles/{profile_id}")


def test_stored_api_key_is_write_only(client):
    name = f"contract-{uuid.uuid4().hex[:8]}"
    created = _create(client, name, api_key="sk-contract-secret")
    try:
        assert created["has_key"] is True
        assert "api_key" not in created
        listed = client.get("/api/v1/model-profiles")
        assert "sk-contract-secret" not in listed.text
    finally:
        _delete(client, created["id"])


def test_patch_omitting_api_key_keeps_it(client):
    name = f"contract-{uuid.uuid4().hex[:8]}"
    created = _create(client, name, api_key="sk-contract-secret")
    try:
        patched = client.patch(
            f"/api/v1/model-profiles/{created['id']}", json=_payload(name, model="contract-model-2")
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["has_key"] is True
        assert patched.json()["model"] == "contract-model-2"
    finally:
        _delete(client, created["id"])


def test_empty_string_clears_api_key(client):
    name = f"contract-{uuid.uuid4().hex[:8]}"
    created = _create(client, name, api_key="sk-contract-secret")
    try:
        cleared = client.patch(
            f"/api/v1/model-profiles/{created['id']}", json=_payload(name, api_key="")
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["has_key"] is False
    finally:
        _delete(client, created["id"])
