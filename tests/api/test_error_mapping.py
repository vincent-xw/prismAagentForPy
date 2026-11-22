from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.main import create_app


def make_app(tmp_path: Path) -> FastAPI:
    application = create_app(
        Settings(
            database_path=tmp_path / "agent.db",
            environment="test",
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


def test_agent_error_is_mapped_without_internal_details(tmp_path: Path) -> None:
    application = make_app(tmp_path)

    with TestClient(application) as client:
        response = client.get("/api/v1/conflict")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "RUN_CONFLICT"
    assert body["error"]["message"] == "当前 Session 已有活动 Run"
    assert body["error"]["details"] == {"session_id": "session-1"}
    assert "Traceback" not in response.text


def test_unclassified_error_returns_internal_without_message(tmp_path: Path) -> None:
    application = make_app(tmp_path)

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


def test_validation_error_uses_unified_error_shape(tmp_path: Path) -> None:
    application = make_app(tmp_path)

    with TestClient(application) as client:
        response = client.get("/api/v1/validate", params={"value": "bad"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
