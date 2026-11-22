import asyncio

import pytest
from tests.api.conftest import ApiTestContext

from prism_agent_kit.api.routes.runs import iter_run_events
from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.core.enums import EventType, RunStatus
from prism_agent_kit.core.models import RunEvent
from prism_agent_kit.core.ports import EventEnvelope


async def test_sse_replays_events_after_last_event_id(
    api_context: ApiTestContext,
) -> None:
    session = (await api_context.client.post("/api/v1/sessions", json={"title": "demo"})).json()
    run = (
        await api_context.client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "hello"},
        )
    ).json()

    async with api_context.uow_factory() as uow:
        first = (await uow.events.list_after(run["id"]))[0]
        second = await uow.events.append(
            RunEvent(
                run_id=run["id"],
                event_type=EventType.RUN_STARTED,
                payload={},
            )
        )
        await uow.commit()

    response = await api_context.client.get(
        f"/api/v1/runs/{run['id']}/events",
        headers={"Last-Event-ID": str(first.id)},
        params={"once": "true"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert f"id: {second.id}" in response.text
    assert f"id: {first.id}\n" not in response.text


async def test_transient_delta_has_no_id_and_terminal_event_closes_stream() -> None:
    bus = RunEventBus()
    stream = iter_run_events(bus, "run-1", after_event_id=None)
    next_event = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)

    await bus.publish(
        EventEnvelope(
            run_id="run-1",
            event_type=EventType.MESSAGE_DELTA,
            payload={"text": "你"},
        )
    )
    delta = await next_event
    assert delta.id is None
    assert delta.event == "message.delta"

    await bus.publish(
        EventEnvelope(
            event_id=9,
            run_id="run-1",
            event_type=EventType.RUN_SUCCEEDED,
            payload={"status": "succeeded"},
        )
    )
    terminal = await anext(stream)

    assert terminal.id == "9"
    assert terminal.event == "run.succeeded"
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def test_terminal_run_reconnect_is_finite(
    api_context: ApiTestContext,
) -> None:
    session = (await api_context.client.post("/api/v1/sessions", json={"title": "demo"})).json()
    run = (
        await api_context.client.post(
            f"/api/v1/sessions/{session['id']}/runs",
            json={"input": "hello"},
        )
    ).json()

    async with api_context.uow_factory() as uow:
        await uow.runs.claim_next()
        await uow.runs.transition(
            run["id"],
            RunStatus.SUCCEEDED,
            output_text="done",
        )
        terminal = await uow.events.append(
            RunEvent(
                run_id=run["id"],
                event_type=EventType.RUN_SUCCEEDED,
                payload={"output": "done"},
            )
        )
        await uow.commit()

    response = await asyncio.wait_for(
        api_context.client.get(f"/api/v1/runs/{run['id']}/events"),
        timeout=1,
    )

    assert response.status_code == 200
    assert "event: run.succeeded" in response.text

    seen_terminal = await asyncio.wait_for(
        api_context.client.get(
            f"/api/v1/runs/{run['id']}/events",
            headers={"Last-Event-ID": str(terminal.id)},
        ),
        timeout=1,
    )

    assert seen_terminal.status_code == 200
    assert "event: run.succeeded" not in seen_terminal.text
