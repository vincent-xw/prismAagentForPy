from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.main import create_app


def make_app(database_path: Path) -> FastAPI:
    application = create_app(
        Settings(
            database_path=database_path,
            environment="test",
            model_name="test-model",
            model_api_key=SecretStr("test-key"),
            model_context_window=4096,
            model_max_output_tokens=256,
            model_token_encoding="cl100k_base",
        )
    )

    @application.get("/api/v1/conflict")
    async def conflict() -> None:
        raise AgentKitError(
            ErrorCode.RUN_CONFLICT,
            "当前 Session 已有活动 Run",
            http_status=409,
            details={"session_id": "session-1"},
        )

    @application.get("/api/v1/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    @application.get("/api/v1/validate")
    async def validate(value: int) -> dict[str, int]:
        return {"value": value}

    return application


def test_agent_error_is_mapped_without_internal_details(
    migrated_database_path: Path,
) -> None:
    application = make_app(migrated_database_path)

    with TestClient(application) as client:
        response = client.get("/api/v1/conflict")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "RUN_CONFLICT"
    assert body["error"]["message"] == "当前 Session 已有活动 Run"
    assert body["error"]["details"] == {"session_id": "session-1"}
    assert "Traceback" not in response.text


def test_unclassified_error_returns_internal_without_message(
    migrated_database_path: Path,
) -> None:
    application = make_app(migrated_database_path)

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


def test_validation_error_uses_unified_error_shape(
    migrated_database_path: Path,
) -> None:
    application = make_app(migrated_database_path)

    with TestClient(application) as client:
        response = client.get("/api/v1/validate", params={"value": "bad"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_unknown_route_uses_unified_error_shape(
    migrated_database_path: Path,
) -> None:
    application = make_app(migrated_database_path)

    with TestClient(application) as client:
        response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_method_not_allowed_uses_unified_error_shape(
    migrated_database_path: Path,
) -> None:
    application = make_app(migrated_database_path)

    with TestClient(application) as client:
        response = client.post("/api/v1/validate")

    assert response.status_code == 405
    body = response.json()
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"
