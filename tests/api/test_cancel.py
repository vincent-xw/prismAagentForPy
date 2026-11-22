from tests.api.conftest import ApiTestContext
from tests.api.helpers import seed_waiting_remote_run

from prism_agent_kit.core.enums import ToolCallStatus
from prism_agent_kit.core.models import Run


async def test_cancel_queued_run_is_immediate_and_idempotent(
    api_context: ApiTestContext,
) -> None:
    session = (await api_context.client.post("/api/v1/sessions", json={})).json()
    run = (
        await api_context.client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "hello"},
        )
    ).json()

    first = await api_context.client.post(f"/api/v1/runs/{run['id']}/cancel")
    second = await api_context.client.post(f"/api/v1/runs/{run['id']}/cancel")

    assert first.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert second.status_code == 200
    assert second.json()["status"] == "cancelled"


async def test_cancel_waiting_run_closes_pending_remote_tool(
    api_context: ApiTestContext,
) -> None:
    run, call = await seed_waiting_remote_run(api_context.uow_factory)

    response = await api_context.client.post(f"/api/v1/runs/{run.id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    async with api_context.uow_factory() as uow:
        stored_call = await uow.tool_calls.get(run.id, call.id)
        messages = await uow.messages.list_for_session(run.session_id)
        events = await uow.events.list_after(run.id)
    assert stored_call.status is ToolCallStatus.CANCELLED
    assert any(message.tool_call_id == call.id for message in messages)
    assert any(event.event_type.value == "run.cancelled" for event in events)


async def test_cancel_running_run_signals_worker(
    api_context: ApiTestContext,
) -> None:
    session = (await api_context.client.post("/api/v1/sessions", json={})).json()
    created = (
        await api_context.client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "hello"},
        )
    ).json()
    async with api_context.uow_factory() as uow:
        claimed = await uow.runs.claim_next()
        await uow.commit()
    assert claimed is not None
    assert claimed.id == created["id"]
    cancel_signal = api_context.cancellation_registry.register(created["id"])

    response = await api_context.client.post(f"/api/v1/runs/{created['id']}/cancel")

    assert response.status_code == 200
    assert cancel_signal.is_set()
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["cancel_requested_at"] is not None

    async with api_context.uow_factory() as uow:
        stored: Run = await uow.runs.get(created["id"])
    assert stored.cancel_requested_at is not None
