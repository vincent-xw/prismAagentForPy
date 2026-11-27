"""GET /sessions/{id}/context 的字段与阈值语义。"""


def test_context_usage_defaults(api_client) -> None:
    session = api_client.post("/api/v1/sessions", json={"title": "ctx"}).json()

    response = api_client.get(f"/api/v1/sessions/{session['id']}/context")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "context_window",
        "max_output_tokens",
        "budget_tokens",
        "used_tokens",
        "percent",
        "threshold",
        "needs_compaction",
        "compactable",
        "last_compaction",
    }
    assert body["context_window"] > body["max_output_tokens"] > 0
    assert body["budget_tokens"] >= 1024
    assert body["threshold"] == 0.85
    assert body["used_tokens"] == 0
    assert body["compactable"] is False
    assert body["last_compaction"] is None


def test_context_usage_counts_messages(api_client) -> None:
    session = api_client.post("/api/v1/sessions", json={"title": "ctx2"}).json()
    created = api_client.post(
        f"/api/v1/sessions/{session['id']}/runs", json={"input": "hello world"}
    )
    assert created.status_code == 202, created.text

    body = api_client.get(f"/api/v1/sessions/{session['id']}/context").json()

    assert body["used_tokens"] > 0
    assert body["percent"] >= 0


def test_context_usage_unknown_session_is_404(api_client) -> None:
    response = api_client.get("/api/v1/sessions/missing/context")
    assert response.status_code == 404
