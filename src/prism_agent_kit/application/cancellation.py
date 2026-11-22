import asyncio


class RunCancellationRegistry:
    """保存正在执行 Run 的协作式取消信号。"""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def register(self, run_id: str) -> asyncio.Event:
        """注册 Run 并返回取消信号。重复注册返回同一信号。"""
        event = self._events.get(run_id)
        if event is None:
            event = asyncio.Event()
            self._events[run_id] = event
        return event

    def get(self, run_id: str) -> asyncio.Event | None:
        return self._events.get(run_id)

    def cancel(self, run_id: str) -> bool:
        """请求取消正在执行的 Run。未注册时返回 False。"""
        event = self._events.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    def unregister(self, run_id: str) -> None:
        self._events.pop(run_id, None)

    def clear(self) -> None:
        self._events.clear()
