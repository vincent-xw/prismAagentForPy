import json
import os
import stat
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr

from prism_agent_kit.application.container import ApplicationContainer
from prism_agent_kit.application.run_worker import RunWorker
from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.enums import ExecutionMode
from prism_agent_kit.core.ports import ModelResponse, ToolCallDraft
from prism_agent_kit.main import create_app
from prism_agent_kit.tools.contracts import ToolDefinition
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.testing import WaitForHostInput
from tests.fakes import ScriptedModelProvider


def make_settings(database_path: Path, **overrides: object) -> Settings:
    """构造不访问外网且模型配置完整的测试设置。"""
    values: dict[str, object] = {
        "database_path": database_path,
        "environment": "test",
        "api_token": None,
        "model_name": "test-model",
        "model_base_url": "https://example.test/v1",
        "model_api_key": SecretStr("test-key"),
        "model_context_window": 8192,
        "model_max_output_tokens": 512,
        "model_token_encoding": "cl100k_base",
        "max_steps": 5,
        "worker_concurrency": 1,
        "session_title_generation_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def make_remote_tool() -> ToolDefinition:
    """返回 E2E 使用的远端工具。"""
    return ToolDefinition(
        name="wait_for_host",
        description="等待外部宿主回填结果",
        input_model=WaitForHostInput,
        output_model=None,
        execution_mode=ExecutionMode.REMOTE,
        timeout_seconds=300,
    )


def wait_for_run_status(
    client: TestClient,
    run_id: str,
    expected: set[str],
    *,
    timeout_seconds: float = 3,
) -> dict[str, object]:
    """轮询 Run 直到进入期望状态。"""
    deadline = time.monotonic() + timeout_seconds
    last_status = "missing"
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        last_status = payload["status"]
        if last_status in expected:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Run 未进入 {expected}: 最后状态为 {last_status}")


def tool_input_digest(client: TestClient, run_id: str) -> str:
    """从持久事件中读取远端工具输入摘要。"""
    response = client.get(
        f"/api/v1/runs/{run_id}/events",
        params={"once": "true"},
    )
    assert response.status_code == 200
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line.removeprefix("data: "))
        if payload["type"] == "tool.requested":
            return str(payload["input_digest"])
    raise AssertionError("未找到 tool.requested 事件")


def test_text_run_streams_and_persists_history(
    migrated_database_path: Path,
) -> None:
    provider = ScriptedModelProvider([ModelResponse(text="hello back")])
    settings = make_settings(migrated_database_path)
    container = ApplicationContainer(settings, model_provider=provider)
    application = create_app(settings, container_factory=lambda _: container)

    with TestClient(application) as client:
        session = client.post("/api/v1/sessions", json={"title": "demo"}).json()
        run = client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "hello", "prompt_ref": "default@1"},
        ).json()

        wait_for_run_status(client, run["id"], {"succeeded"})
        events = client.get(
            f"/api/v1/runs/{run['id']}/events",
            params={"once": "true"},
        )
        messages = client.get(f"/api/v1/sessions/{session['id']}/messages").json()

    assert "event: run.succeeded" in events.text
    assert [item["role"] for item in messages["items"]] == ["user", "assistant"]
    assert messages["items"][1]["content"] == "hello back"


def test_remote_tool_survives_worker_restart(
    migrated_database_path: Path,
) -> None:
    settings = make_settings(migrated_database_path)
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCallDraft(
                        call_id="call-1",
                        tool_name="wait_for_host",
                        input={"value": "one"},
                    )
                ]
            ),
            ModelResponse(text="tool completed"),
        ]
    )
    registry = ToolRegistry()
    registry.register(make_remote_tool())

    first_container = ApplicationContainer(
        settings,
        model_provider=provider,
        tool_registry=registry,
    )
    first_app = create_app(settings, container_factory=lambda _: first_container)
    with TestClient(first_app) as client:
        session = client.post("/api/v1/sessions", json={}).json()
        run = client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "use tool"},
        ).json()
        wait_for_run_status(client, run["id"], {"waiting_for_tool"})
        digest = tool_input_digest(client, run["id"])

    second_container = ApplicationContainer(
        settings,
        model_provider=provider,
        tool_registry=registry,
    )
    second_app = create_app(settings, container_factory=lambda _: second_container)
    with TestClient(second_app) as client:
        result = client.post(
            f"/api/v1/runs/{run['id']}/tool-calls/call-1/result",
            json={
                "ok": True,
                "input_digest": digest,
                "output": {"value": "one"},
            },
        )
        assert result.status_code == 200
        wait_for_run_status(client, run["id"], {"succeeded"})
        messages = client.get(f"/api/v1/sessions/{session['id']}/messages").json()

    assert [item["role"] for item in messages["items"]] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert messages["items"][-1]["content"] == "tool completed"


async def test_second_container_cannot_lock_same_database(
    migrated_database_path: Path,
) -> None:
    settings = make_settings(migrated_database_path)
    provider = ScriptedModelProvider([])
    first = ApplicationContainer(settings, model_provider=provider)
    second = ApplicationContainer(settings, model_provider=provider)

    await first.start()
    try:
        with pytest.raises(RuntimeError, match="数据库"):
            await second.start()
    finally:
        await second.stop()
        await first.stop()


async def test_container_requires_explicit_model_budget_configuration(
    migrated_database_path: Path,
) -> None:
    settings = make_settings(
        migrated_database_path,
        model_context_window=None,
    )
    container = ApplicationContainer(settings)

    with pytest.raises(RuntimeError, match="MODEL_CONTEXT_WINDOW"):
        await container.start()
    await container.stop()


async def test_container_secures_new_database_directory_before_file_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "posix":
        return
    database_path = tmp_path / "container-private" / "agent.db"
    settings = make_settings(database_path)
    container = ApplicationContainer(
        settings,
        model_provider=ScriptedModelProvider([]),
    )

    async def skip_worker_start(worker: RunWorker) -> None:
        return None

    monkeypatch.setattr(RunWorker, "start", skip_worker_start)
    await container.start()
    try:
        assert stat.S_IMODE(database_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(database_path.stat().st_mode) == 0o600
    finally:
        await container.stop()


def test_e2e_write_requires_approval_then_completes(
    migrated_database_path: Path,
    tmp_path: Path,
) -> None:
    """完整链路：模型请求写文件 → Run 等审批 → 批准 → 文件落盘且 Run 完成。"""
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                text="",
                reasoning=None,
                tool_calls=[
                    ToolCallDraft(
                        call_id="c1",
                        tool_name="file_write",
                        input={"path": "notes.md", "content": "hello", "mode": "overwrite"},
                    )
                ],
            ),
            ModelResponse(text="done", reasoning=None, tool_calls=[]),
        ]
    )
    settings = make_settings(migrated_database_path, api_token=None)
    container = ApplicationContainer(settings, model_provider=provider)
    application = create_app(settings, container_factory=lambda _: container)
    workspace_root = tmp_path / "ws"
    workspace_root.mkdir()

    with TestClient(application) as client:
        created = client.post("/api/v1/workspaces", json={"path": str(workspace_root)})
        assert created.status_code == 200
        session = client.post("/api/v1/sessions", json={"title": "demo"}).json()
        run = client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "write notes"},
        ).json()

        wait_for_run_status(client, run["id"], {"waiting_for_approval"})
        approval = client.post(
            f"/api/v1/runs/{run['id']}/tool-calls/c1/approval",
            json={"decision": "approve"},
        )
        assert approval.status_code == 200, approval.text
        wait_for_run_status(client, run["id"], {"succeeded"})

    assert (workspace_root / "notes.md").read_text(encoding="utf-8") == "hello"


def test_e2e_mcp_tool_requires_approval(
    migrated_database_path: Path,
) -> None:
    """MCP 工具调用必须审批：等待审批 → 批准 → Run 完成并回填结果。"""

    class EchoInput(BaseModel):
        text: str

    async def echo_handler(raw: EchoInput, _context: object) -> dict[str, object]:
        return {"text": raw.text}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="mcp__demo__echo",
            description="mcp echo",
            input_model=EchoInput,
            output_model=None,
            execution_mode=ExecutionMode.LOCAL,
            timeout_seconds=5,
            requires_approval=True,
            handler=echo_handler,
        )
    )
    provider = ScriptedModelProvider(
        [
            ModelResponse(
                text="",
                reasoning=None,
                tool_calls=[
                    ToolCallDraft(call_id="c1", tool_name="mcp__demo__echo", input={"text": "hi"})
                ],
            ),
            ModelResponse(text="done", reasoning=None, tool_calls=[]),
        ]
    )
    settings = make_settings(migrated_database_path, api_token=None)
    container = ApplicationContainer(settings, model_provider=provider, tool_registry=registry)
    application = create_app(settings, container_factory=lambda _: container)

    with TestClient(application) as client:
        session = client.post("/api/v1/sessions", json={"title": "demo"}).json()
        run = client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "echo hi"},
        ).json()

        wait_for_run_status(client, run["id"], {"waiting_for_approval"})
        preview = client.get(f"/api/v1/runs/{run['id']}/tool-calls/c1/preview")
        assert preview.status_code == 200, preview.text
        assert preview.json()["kind"] == "generic"
        decision = client.post(
            f"/api/v1/runs/{run['id']}/tool-calls/c1/approval",
            json={"decision": "approve"},
        )
        assert decision.status_code == 200, decision.text
        wait_for_run_status(client, run["id"], {"succeeded"})

        calls = client.get(f"/api/v1/runs/{run['id']}/tool-calls")
        if calls.status_code == 200:
            assert calls.json()[0]["output"] == {"text": "hi"}
