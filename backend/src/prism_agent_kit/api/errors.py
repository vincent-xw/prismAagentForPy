import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from prism_agent_kit.api.request_context import create_request_id, get_request_id
from prism_agent_kit.core.errors import AgentKitError, ErrorCode

logger = logging.getLogger(__name__)


def make_error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    request_id: str,
    details: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """构造统一错误响应并确保响应头与正文中的请求标识一致。"""
    response_headers = dict(headers) if headers is not None else {}
    response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code.value,
                "message": message,
                "request_id": request_id,
                "details": dict(details) if details is not None else {},
            }
        },
        headers=response_headers,
    )


def _resolve_request_id(request: Request) -> str:
    """从请求状态或当前上下文取得请求标识。"""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id

    request_id = get_request_id() or create_request_id()
    request.state.request_id = request_id
    return request_id


def _validation_details(exc: RequestValidationError) -> dict[str, object]:
    """只暴露稳定的校验位置和原因。不回显输入值或异常上下文。"""
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        errors.append(
            {
                "loc": list(error.get("loc", ())),
                "msg": str(error.get("msg", "输入无效")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return {"errors": errors}


def install_exception_handlers(app: FastAPI) -> None:
    """注册 API 统一异常处理器。"""

    async def handle_agent_error(request: Request, exc: Exception) -> JSONResponse:
        """映射领域异常并保留其稳定 HTTP 状态。"""
        if not isinstance(exc, AgentKitError):
            raise exc

        request_id = _resolve_request_id(request)
        logger.warning(
            "API 领域错误 request_id=%s status=%s code=%s path=%s",
            request_id,
            exc.http_status,
            exc.code.value,
            request.url.path,
        )
        return make_error_response(
            status_code=exc.http_status,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            details=exc.details,
        )

    async def handle_validation_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """将 FastAPI 参数校验错误转换为统一结构。"""
        if not isinstance(exc, RequestValidationError):
            raise exc

        request_id = _resolve_request_id(request)
        logger.info(
            "API 参数校验失败 request_id=%s path=%s",
            request_id,
            request.url.path,
        )
        return make_error_response(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="请求参数校验失败",
            request_id=request_id,
            details=_validation_details(exc),
        )

    async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
        """把框架产生的路由错误转换为统一错误结构。"""
        if not isinstance(exc, StarletteHTTPException):
            raise exc

        if exc.status_code == 404:
            code = ErrorCode.NOT_FOUND
            message = "请求的路由不存在"
        elif exc.status_code == 405:
            code = ErrorCode.METHOD_NOT_ALLOWED
            message = "请求方法不允许"
        else:
            code = ErrorCode.INVALID_REQUEST
            message = "请求无法处理"
        return make_error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            request_id=_resolve_request_id(request),
            headers=exc.headers,
        )

    async def handle_unclassified_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """记录内部异常但只向客户端返回脱敏错误。"""
        request_id = _resolve_request_id(request)
        logger.exception(
            "API 未分类异常 request_id=%s path=%s",
            request_id,
            request.url.path,
            exc_info=exc,
        )
        return make_error_response(
            status_code=500,
            code=ErrorCode.INTERNAL,
            message="服务内部错误",
            request_id=request_id,
        )

    app.add_exception_handler(AgentKitError, handle_agent_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unclassified_error)
