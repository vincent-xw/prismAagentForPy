import httpx


def test_ui_serves_spa(ui_base_url):
    response = httpx.get(f"{ui_base_url}/", timeout=10.0)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_ui_proxies_api_health(ui_base_url):
    response = httpx.get(f"{ui_base_url}/api/v1/health", timeout=10.0)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_404_is_json_not_html(ui_base_url, token):
    # 未带 Token 时鉴权先于路由（401）；带 Token 才能看到 404 信封。
    response = httpx.get(
        f"{ui_base_url}/api/v1/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_spa_route_falls_back_to_index(ui_base_url):
    response = httpx.get(f"{ui_base_url}/sessions/abc", timeout=10.0)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
