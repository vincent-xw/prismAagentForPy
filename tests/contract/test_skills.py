"""Skills 契约：列表、详情、资源与 Run 注入。"""

import time


def test_lists_shared_skill(client):
    response = client.get("/api/v1/skills")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    demo = next((item for item in items if item["name"] == "prism-demo"), None)
    assert demo is not None, items
    assert set(demo) == {"name", "description", "path", "root", "shadowed"}
    assert demo["shadowed"] is False
    assert demo["description"]


def test_skill_detail_has_resources(client):
    response = client.get("/api/v1/skills/prism-demo")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "Prism 演示技能" in body["content"]
    assert any(
        item["path"] == "references/checklist.md" and item["kind"] == "references"
        for item in body["resources"]
    )


def test_unknown_skill_is_rejected(client):
    response = client.get("/api/v1/skills/no-such-skill")

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"


def test_run_with_skill_injects_context(client):
    session = client.post("/api/v1/sessions", json={"title": "skill-contract"})
    assert session.status_code in {200, 201}, session.text
    session_id = session.json()["id"]

    created = client.post(
        f"/api/v1/sessions/{session_id}/runs",
        json={"input": "按技能回答", "skill_name": "prism-demo"},
    )
    assert created.status_code == 202, created.text

    for _ in range(20):
        items = client.get(f"/api/v1/sessions/{session_id}/messages").json()["items"]
        if len(items) >= 2:
            break
        time.sleep(0.5)

    assert items[0]["kind"] == "skill_context"
    assert "<skill_content name=\"prism-demo\">" in items[0]["content"]
    assert items[1]["content"] == "按技能回答"


def test_run_with_unknown_skill_is_422(client):
    session = client.post("/api/v1/sessions", json={"title": "skill-contract-2"}).json()

    response = client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "hi", "skill_name": "no-such-skill"},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"
