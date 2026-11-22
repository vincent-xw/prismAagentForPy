from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from prism_agent_kit.core.config import Settings
from prism_agent_kit.main import create_app


def make_app(
    database_path: Path,
    *,
    api_token: SecretStr | None,
) -> FastAPI:
    application = create_app(
        Settings(
            database_path=database_path,
            environment="test",
            api_token=api_token,
            model_name="test-model",
            model_api_key=SecretStr("test-key"),
            model_context_window=4096,
            model_max_output_tokens=256,
            model_token_encoding="cl100k_base",
        )
    )

    @application.get("/api/v1/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    return application


def test_missing_token_returns_401(migrated_database_path: Path) -> None:
    application = make_app(migrated_database_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get("/api/v1/protected")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_invalid_token_returns_401(migrated_database_path: Path) -> None:
    application = make_app(migrated_database_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer wrong"},
        )

    assert response.status_code == 401


def test_valid_token_allows_request(migrated_database_path: Path) -> None:
    application = make_app(migrated_database_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_health_is_always_exempt(migrated_database_path: Path) -> None:
    application = make_app(migrated_database_path, api_token=SecretStr("secret"))

    with TestClient(application) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")


def test_auth_can_be_disabled_in_test_environment(migrated_database_path: Path) -> None:
    application = make_app(migrated_database_path, api_token=None)

    with TestClient(application) as client:
        response = client.get("/api/v1/protected")

    assert response.status_code == 200


def test_non_test_environment_requires_token(migrated_database_path: Path) -> None:
    application = create_app(
        Settings(
            database_path=migrated_database_path,
            environment="development",
            api_token=None,
            model_name="test-model",
            model_api_key=SecretStr("test-key"),
            model_context_window=4096,
            model_max_output_tokens=256,
            model_token_encoding="cl100k_base",
        )
    )

    with pytest.raises(RuntimeError, match="API_TOKEN"), TestClient(application):
        pass
