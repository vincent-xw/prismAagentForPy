from collections.abc import Mapping
from enum import StrEnum


class ErrorCode(StrEnum):
    """对外稳定的错误码。该值不随内部异常类型变化。"""

    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    TOOL_CALL_NOT_FOUND = "TOOL_CALL_NOT_FOUND"
    RUN_CONFLICT = "RUN_CONFLICT"
    INVALID_RUN_TRANSITION = "INVALID_RUN_TRANSITION"
    PROMPT_NOT_FOUND = "PROMPT_NOT_FOUND"
    INVALID_PROMPT_REF = "INVALID_PROMPT_REF"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_TOOL_DEFINITION = "INVALID_TOOL_DEFINITION"
    TOOL_INPUT_INVALID = "TOOL_INPUT_INVALID"
    TOOL_OUTPUT_INVALID = "TOOL_OUTPUT_INVALID"
    TOOL_RESULT_CONFLICT = "TOOL_RESULT_CONFLICT"
    TOOL_CALL_EXPIRED = "TOOL_CALL_EXPIRED"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_EXECUTION_TIMEOUT = "TOOL_EXECUTION_TIMEOUT"
    REMOTE_TOOL_TIMEOUT = "REMOTE_TOOL_TIMEOUT"
    RUN_CANCELLED = "RUN_CANCELLED"
    PROCESS_INTERRUPTED = "PROCESS_INTERRUPTED"
    CONTEXT_BUDGET_EXCEEDED = "CONTEXT_BUDGET_EXCEEDED"
    INVALID_HISTORY = "INVALID_HISTORY"
    HARNESS_STEP_LIMIT = "HARNESS_STEP_LIMIT"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_UPSTREAM_ERROR = "MODEL_UPSTREAM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AgentKitError(Exception):
    """携带稳定错误码与 HTTP 映射的领域异常。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        http_status: int = 500,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = dict(details) if details is not None else {}
