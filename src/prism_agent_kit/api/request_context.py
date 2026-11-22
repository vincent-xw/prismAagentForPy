from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def create_request_id() -> str:
    """创建不可预测的请求标识。"""
    return f"req_{uuid4().hex}"


def get_request_id() -> str | None:
    """返回当前协程上下文的请求标识。"""
    return _request_id.get()


class RequestIdMiddleware:
    """为每个 HTTP 请求生成请求标识并写入响应头。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = create_request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        token: Token[str | None] = _request_id.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            """在响应开始时补充请求标识响应头。"""
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id.reset(token)
