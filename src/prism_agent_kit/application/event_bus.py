import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from prism_agent_kit.core.ports import EventEnvelope

type ReplayLoader = Callable[
    [str, int | None],
    Awaitable[list[EventEnvelope]],
]


class RunEventBus:
    """合并数据库重放事件与进程内实时事件的发布订阅总线。"""

    def __init__(self, replay_loader: ReplayLoader | None = None) -> None:
        self._replay_loader = replay_loader
        self._subscribers: dict[
            str,
            set[asyncio.Queue[EventEnvelope | None]],
        ] = {}
        self._closed = False

    async def subscribe(
        self,
        run_id: str,
        after_event_id: int | None,
    ) -> AsyncIterator[EventEnvelope]:
        """先注册实时订阅。再重放持久事件并按 ID 去重。"""
        queue: asyncio.Queue[EventEnvelope | None] = asyncio.Queue()
        subscribers = self._subscribers.setdefault(run_id, set())
        subscribers.add(queue)
        seen_event_ids: set[int] = set()
        try:
            if self._replay_loader is not None:
                replay = await self._replay_loader(run_id, after_event_id)
                for replayed in replay:
                    if self._should_skip(
                        replayed,
                        after_event_id,
                        seen_event_ids,
                    ):
                        continue
                    yield replayed

            while True:
                live_event = await queue.get()
                if live_event is None:
                    return
                if self._should_skip(
                    live_event,
                    after_event_id,
                    seen_event_ids,
                ):
                    continue
                yield live_event
        finally:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    async def publish(self, event: EventEnvelope) -> None:
        """向 Run 的全部实时订阅者广播事件。"""
        if self._closed:
            return
        for queue in list(self._subscribers.get(event.run_id, ())):
            queue.put_nowait(event)

    async def close(self) -> None:
        """停止总线并唤醒全部订阅者。"""
        self._closed = True
        subscribers = [queue for queues in self._subscribers.values() for queue in queues]
        self._subscribers.clear()
        for queue in subscribers:
            queue.put_nowait(None)

    @staticmethod
    def _should_skip(
        event: EventEnvelope,
        after_event_id: int | None,
        seen_event_ids: set[int],
    ) -> bool:
        """持久事件按游标过滤。临时事件永远保留。"""
        if event.event_id is None:
            return False
        if after_event_id is not None and event.event_id <= after_event_id:
            return True
        if event.event_id in seen_event_ids:
            return True
        seen_event_ids.add(event.event_id)
        return False
