def test_create_run_with_unknown_skill(api_client) -> None:
    session = api_client.post("/api/v1/sessions", json={"title": "demo"}).json()

    response = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "hi", "skill_name": "nope"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"


def test_create_run_with_skill_writes_skill_message(api_client) -> None:
    session = api_client.post("/api/v1/sessions", json={"title": "demo"}).json()

    created = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "hi", "skill_name": "pdf-tools"},
    )
    assert created.status_code == 202, created.text

    messages = api_client.get(f"/api/v1/sessions/{session['id']}/messages").json()["items"]
    assert [item["kind"] for item in messages] == ["skill_context", "text"]
