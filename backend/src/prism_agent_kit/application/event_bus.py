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
        """先注册实时订阅, 再按数据库游标补齐可能乱序到达的持久事件。"""
        queue: asyncio.Queue[EventEnvelope | None] = asyncio.Queue()
        subscribers = self._subscribers.setdefault(run_id, set())
        subscribers.add(queue)
        last_event_id = after_event_id
        try:
            if self._replay_loader is not None:
                replay = await self._replay_loader(run_id, after_event_id)
                for replayed in replay:
                    event_id = replayed.event_id
                    if event_id is None:
                        yield replayed
                        continue
                    if last_event_id is not None and event_id <= last_event_id:
                        continue
                    last_event_id = event_id
                    yield replayed

            while True:
                live_event = await queue.get()
                if live_event is None:
                    return
                if live_event.event_id is None:
                    yield live_event
                    continue
                if last_event_id is not None and live_event.event_id <= last_event_id:
                    continue

                # 实时发布由多个服务并发触发, 到达顺序不一定等于 SQLite 提交顺序。
                # 在输出终态前补读数据库游标, 避免客户端收到终态后永久丢失中间事件。
                caught_up = await self._load_until(
                    run_id,
                    after_event_id=last_event_id,
                    through_event_id=live_event.event_id,
                )
                for stored_event in caught_up:
                    event_id = stored_event.event_id
                    if event_id is None:
                        continue
                    if last_event_id is not None and event_id <= last_event_id:
                        continue
                    last_event_id = event_id
                    yield stored_event

                # SQLite 已提交但读取快照暂时不可见时仍发送实时事件。
                if last_event_id is None or live_event.event_id > last_event_id:
                    last_event_id = live_event.event_id
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

    async def _load_until(
        self,
        run_id: str,
        *,
        after_event_id: int | None,
        through_event_id: int,
    ) -> list[EventEnvelope]:
        """读取游标之后且不超过触发事件的持久记录。"""
        if self._replay_loader is None:
            return []
        events = await self._replay_loader(run_id, after_event_id)
        return [
            event
            for event in events
            if event.event_id is not None and event.event_id <= through_event_id
        ]
