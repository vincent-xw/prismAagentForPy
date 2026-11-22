from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from prism_agent_kit.core.config import Settings
from prism_agent_kit.main import create_app


def make_app(
    tmp_path: Path,
    *,
    api_token: SecretStr | None,
) -> FastAPI:
    application = create_app(
        Settings(
            database_path=tmp_path / "agent.db",
            environment="test",
            api_token=api_token,
        )
    )

    @application.get("/api/v1/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    return application


def test_missing_token_returns_401(tmp_path: Path) -> None:
    application = make_app(tmp_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get("/api/v1/protected")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_invalid_token_returns_401(tmp_path: Path) -> None:
    application = make_app(tmp_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer wrong"},
        )

    assert response.status_code == 401


def test_valid_token_allows_request(tmp_path: Path) -> None:
    application = make_app(tmp_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_health_is_always_exempt(tmp_path: Path) -> None:
    application = make_app(tmp_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")


def test_auth_can_be_disabled_in_test_environment(tmp_path: Path) -> None:
    application = make_app(tmp_path, api_token=None)

    with TestClient(application) as client:
        response = client.get("/api/v1/protected")

    assert response.status_code == 200


def test_non_test_environment_requires_token(tmp_path: Path) -> None:
    application = create_app(
        Settings(
            database_path=tmp_path / "agent.db",
            environment="development",
            api_token=None,
        )
    )

    with pytest.raises(RuntimeError, match="API_TOKEN"), TestClient(application):
        pass
