from pathlib import Path


def test_list_and_detail(api_client) -> None:
    items = api_client.get("/api/v1/skills").json()["items"]
    assert any(item["name"] == "pdf-tools" for item in items)

    detail = api_client.get("/api/v1/skills/pdf-tools").json()
    assert detail["name"] == "pdf-tools"
    assert detail["content"].startswith("#")


def test_unknown_skill(api_client) -> None:
    response = api_client.get("/api/v1/skills/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"


def test_skill_dirs_fixture(skill_dirs: Path) -> None:
    assert (skill_dirs / "pdf-tools" / "SKILL.md").is_file()
