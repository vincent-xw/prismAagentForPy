"""上下文使用量契约：字段、预算与阈值语义。"""

import uuid


def _session(client) -> str:
    response = client.post("/api/v1/sessions", json={"title": f"ctx-{uuid.uuid4().hex[:6]}"})
    assert response.status_code in {200, 201}, response.text
    return response.json()["id"]


def test_empty_session_reports_zero_usage(client):
    session_id = _session(client)

    response = client.get(f"/api/v1/sessions/{session_id}/context")

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
    assert body["budget_tokens"] == max(1024, body["context_window"] - body["max_output_tokens"] - 2048)
    assert body["used_tokens"] == 0
    assert body["threshold"] == 0.85
    assert body["needs_compaction"] is False
    assert body["compactable"] is False
    assert body["last_compaction"] is None


def test_usage_grows_after_a_run(client):
    session_id = _session(client)
    run = client.post(f"/api/v1/sessions/{session_id}/runs", json={"input": "上下文测试"})
    assert run.status_code == 202, run.text

    response = client.get(f"/api/v1/sessions/{session_id}/context")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["used_tokens"] > 0
    assert body["percent"] > 0
