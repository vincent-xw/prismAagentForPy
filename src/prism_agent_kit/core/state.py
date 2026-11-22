from prism_agent_kit.core.enums import RunStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode

_ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_FOR_TOOL,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.WAITING_FOR_TOOL: frozenset(
        {RunStatus.QUEUED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


def ensure_run_transition(current: RunStatus, target: RunStatus) -> None:
    """校验 Run 状态迁移。非法迁移统一抛出领域异常。"""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise AgentKitError(
            ErrorCode.INVALID_RUN_TRANSITION,
            f"Run 状态不能从 {current.value} 变为 {target.value}",
            http_status=409,
            details={"current": current.value, "target": target.value},
        )
