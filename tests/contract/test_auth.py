import httpx


def test_missing_token_is_401(base_url):
    response = httpx.get(f"{base_url}/api/v1/sessions", timeout=10.0)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_wrong_token_is_401(base_url):
    response = httpx.get(
        f"{base_url}/api/v1/sessions",
        headers={"Authorization": "Bearer wrong-token"},
        timeout=10.0,
    )
    assert response.status_code == 401
