def profile_payload(name: str = "primary", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "base_url": "https://api.example.com/v1",
        "model": "model-a",
        "api_key_env": "OPENAI_API_KEY",
        "context_window": 128000,
        "max_output_tokens": 8192,
    }
    payload.update(overrides)
    return payload


def test_profile_crud_activate_and_probe(api_client) -> None:
    created = api_client.post("/api/v1/model-profiles", json=profile_payload())
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["is_active"] is False

    activated = api_client.post(f"/api/v1/model-profiles/{body['id']}/activate")
    assert activated.status_code == 200 and activated.json()["is_active"] is True

    listed = api_client.get("/api/v1/model-profiles").json()
    assert len(listed) == 1 and listed[0]["is_active"] is True

    probed = api_client.post(f"/api/v1/model-profiles/{body['id']}/probe")
    assert probed.status_code == 200 and probed.json()["ok"] is True

    patched = api_client.patch(
        f"/api/v1/model-profiles/{body['id']}", json=profile_payload(model="model-b")
    )
    assert patched.json()["model"] == "model-b"


def test_delete_active_conflict(api_client) -> None:
    created = api_client.post("/api/v1/model-profiles", json=profile_payload()).json()
    api_client.post(f"/api/v1/model-profiles/{created['id']}/activate")

    response = api_client.delete(f"/api/v1/model-profiles/{created['id']}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MODEL_PROFILE_IN_USE"


def test_invalid_profile_rejected(api_client) -> None:
    response = api_client.post(
        "/api/v1/model-profiles", json=profile_payload(base_url="ftp://example.com")
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MODEL_PROFILE_INVALID"


def test_stored_api_key_is_write_only(api_client) -> None:
    created = api_client.post(
        "/api/v1/model-profiles", json=profile_payload(api_key="sk-secret-value")
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["has_key"] is True
    assert "api_key" not in body
    assert "sk-secret-value" not in created.text

    listed = api_client.get("/api/v1/model-profiles")
    assert "sk-secret-value" not in listed.text


def test_patch_without_api_key_keeps_stored_key(api_client) -> None:
    created = api_client.post(
        "/api/v1/model-profiles", json=profile_payload(api_key="sk-secret-value")
    ).json()

    patched = api_client.patch(
        f"/api/v1/model-profiles/{created['id']}", json=profile_payload(model="model-b")
    )

    assert patched.status_code == 200
    assert patched.json()["has_key"] is True
    assert patched.json()["model"] == "model-b"


def test_patch_with_empty_string_clears_key(api_client, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    created = api_client.post(
        "/api/v1/model-profiles", json=profile_payload(api_key="sk-secret-value")
    ).json()
    assert created["has_key"] is True

    cleared = api_client.patch(
        f"/api/v1/model-profiles/{created['id']}", json=profile_payload(api_key="")
    )

    assert cleared.status_code == 200
    assert cleared.json()["has_key"] is False
