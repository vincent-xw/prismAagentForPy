import asyncio
from collections.abc import Awaitable, Callable

import pytest

from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.core.enums import EventType
from prism_agent_kit.core.ports import EventEnvelope

ReplayLoader = Callable[
    [str, int | None],
    Awaitable[list[EventEnvelope]],
]


def make_bus(events: list[EventEnvelope]) -> RunEventBus:
    async def load(run_id: str, after_event_id: int | None) -> list[EventEnvelope]:
        return [
            event
            for event in events
            if event.run_id == run_id
            and (after_event_id is None or (event.event_id or 0) > after_event_id)
        ]

    return RunEventBus(load)


async def test_event_bus_merges_replay_and_live_without_duplicates() -> None:
    run_id = "run-1"
    bus = make_bus(
        [
            EventEnvelope(
                event_id=2,
                run_id=run_id,
                event_type=EventType.RUN_STARTED,
                payload={},
            )
        ]
    )
    stream = bus.subscribe(run_id, after_event_id=1)

    first = await anext(stream)
    await bus.publish(
        EventEnvelope(
            run_id=run_id,
            event_type=EventType.MESSAGE_DELTA,
            payload={"text": "你"},
        )
    )
    second = await anext(stream)

    assert first.event_id == 2
    assert second.event_type is EventType.MESSAGE_DELTA
    await stream.aclose()


async def test_transient_delta_has_no_durable_event_id() -> None:
    bus = RunEventBus()
    stream = bus.subscribe("run-1", after_event_id=None)
    next_event = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)

    await bus.publish(
        EventEnvelope(
            run_id="run-1",
            event_type=EventType.REASONING_DELTA,
            payload={"text": "thinking"},
        )
    )
    event = await next_event

    assert event.event_id is None
    assert event.event_type is EventType.REASONING_DELTA
    await stream.aclose()


async def test_live_persistent_event_already_replayed_is_deduplicated() -> None:
    run_id = "run-1"
    persisted = EventEnvelope(
        event_id=2,
        run_id=run_id,
        event_type=EventType.RUN_STARTED,
        payload={},
    )
    bus = make_bus([persisted])
    stream = bus.subscribe(run_id, after_event_id=1)

    first = await anext(stream)
    await bus.publish(persisted)
    await bus.publish(
        EventEnvelope(
            run_id=run_id,
            event_type=EventType.MESSAGE_DELTA,
            payload={"text": "next"},
        )
    )
    second = await anext(stream)

    assert first.event_id == 2
    assert second.event_type is EventType.MESSAGE_DELTA
    await stream.aclose()


async def test_close_releases_all_subscribers() -> None:
    bus = RunEventBus()
    stream = bus.subscribe("run-1", after_event_id=None)
    next_event = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    await bus.publish(
        EventEnvelope(
            run_id="run-1",
            event_type=EventType.MESSAGE_DELTA,
            payload={"text": "first"},
        )
    )
    assert await next_event is not None

    await bus.close()

    with pytest.raises(StopAsyncIteration):
        await anext(stream)
