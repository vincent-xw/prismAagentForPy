import hmac
import logging

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from prism_agent_kit.api.errors import make_error_response
from prism_agent_kit.api.request_context import create_request_id
from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.errors import ErrorCode

logger = logging.getLogger(__name__)


def validate_api_token_configuration(settings: Settings) -> None:
    """非测试环境缺少 API Token 时拒绝启动。"""
    if settings.environment == "test":
        return
    if settings.api_token is None or not settings.api_token.get_secret_value():
        raise RuntimeError("非测试环境必须配置 PRISM_AGENT_KIT_API_TOKEN")


class ApiTokenMiddleware:
    """校验本地 API 的 Bearer Token。"""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.environment = settings.environment
        self.health_path = f"{settings.api_prefix.rstrip('/')}/health"
        token = settings.api_token
        self.expected_token = token.get_secret_value() if token is not None else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope["path"]).rstrip("/")
        if path == self.health_path:
            await self.app(scope, receive, send)
            return

        if self.expected_token is None:
            if self.environment == "test":
                await self.app(scope, receive, send)
                return
            raise RuntimeError("非测试环境必须配置 PRISM_AGENT_KIT_API_TOKEN")

        request = Request(scope, receive=receive)
        request_id = getattr(request.state, "request_id", None)
        if not isinstance(request_id, str):
            request_id = create_request_id()
            request.state.request_id = request_id

        authorization = Headers(scope=scope).get("authorization")
        if not self._matches_token(authorization):
            logger.warning(
                "API 鉴权失败 request_id=%s path=%s",
                request_id,
                request.url.path,
            )
            response = make_error_response(
                status_code=401,
                code=ErrorCode.UNAUTHORIZED,
                message="API Token 无效或缺失",
                request_id=request_id,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _matches_token(self, authorization: str | None) -> bool:
        """使用常量时间比较校验 Bearer Token。"""
        if authorization is None:
            return False
        scheme, separator, credential = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not credential:
            return False

        expected = self.expected_token or ""
        return hmac.compare_digest(
            credential.encode("utf-8"),
            expected.encode("utf-8"),
        )
