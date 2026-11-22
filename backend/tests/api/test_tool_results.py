from pydantic import BaseModel
from tests.api.conftest import ApiTestContext
from tests.api.helpers import seed_waiting_remote_run

from prism_agent_kit.core.enums import ExecutionMode, ToolCallStatus
from prism_agent_kit.tools.contracts import ToolDefinition


class SchemaOutput(BaseModel):
    value: str


class EmptyInput(BaseModel):
    pass


async def test_tool_result_requires_matching_digest(
    api_context: ApiTestContext,
) -> None:
    run, call = await seed_waiting_remote_run(api_context.uow_factory)

    response = await api_context.client.post(
        f"/api/v1/runs/{run.id}/tool-calls/{call.id}/result",
        json={"ok": True, "input_digest": "sha256:wrong", "output": {"value": "one"}},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TOOL_INPUT_DIGEST_MISMATCH"


async def test_duplicate_identical_result_is_idempotent(
    api_context: ApiTestContext,
) -> None:
    run, call = await seed_waiting_remote_run(api_context.uow_factory)
    payload = {
        "ok": True,
        "input_digest": call.input_digest,
        "output": {"value": "one"},
    }

    first = await api_context.client.post(
        f"/api/v1/runs/{run.id}/tool-calls/{call.id}/result",
        json=payload,
    )
    duplicate = await api_context.client.post(
        f"/api/v1/runs/{run.id}/tool-calls/{call.id}/result",
        json=payload,
    )
    conflicting = await api_context.client.post(
        f"/api/v1/runs/{run.id}/tool-calls/{call.id}/result",
        json={**payload, "output": {"value": "different"}},
    )

    assert first.status_code == 200
    assert first.json()["status"] == ToolCallStatus.SUCCEEDED.value
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == ToolCallStatus.SUCCEEDED.value
    assert conflicting.status_code == 409
    assert conflicting.json()["error"]["code"] == "TOOL_RESULT_CONFLICT"


async def test_invalid_remote_output_keeps_tool_pending(
    api_context: ApiTestContext,
) -> None:
    api_context.tool_registry.register(
        ToolDefinition(
            name="schema_remote",
            description="返回结构化结果",
            input_model=EmptyInput,
            output_model=SchemaOutput,
            execution_mode=ExecutionMode.REMOTE,
            timeout_seconds=300,
        )
    )
    run, call = await seed_waiting_remote_run(
        api_context.uow_factory,
        tool_name="schema_remote",
        tool_input={},
    )

    response = await api_context.client.post(
        f"/api/v1/runs/{run.id}/tool-calls/{call.id}/result",
        json={"ok": True, "input_digest": call.input_digest, "output": {"wrong": "shape"}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TOOL_OUTPUT_INVALID"

    async with api_context.uow_factory() as uow:
        stored = await uow.tool_calls.get(run.id, call.id)
    assert stored.status is ToolCallStatus.PENDING
