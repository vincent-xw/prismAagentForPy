"""等待态 Run 在工具全部闭合后的去向判定，供审批服务与过期扫描共用。"""

from typing import TYPE_CHECKING

from prism_agent_kit.core.enums import EventType, ExecutionMode, RunStatus, ToolCallStatus
from prism_agent_kit.core.models import RunEvent

if TYPE_CHECKING:
    from prism_agent_kit.db.uow import UnitOfWork

_TERMINAL_TOOL_STATUSES = frozenset(
    {
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
        ToolCallStatus.EXPIRED,
        ToolCallStatus.CANCELLED,
    }
)


async def finalize_waiting_run(uow: "UnitOfWork", run_id: str) -> None:
    """按 spec §11.2 重算等待中 Run 的去向；不提交事务。"""
    run = await uow.runs.get(run_id)
    calls = await uow.tool_calls.list_for_run(run_id)
    if any(call.status is ToolCallStatus.AWAITING_APPROVAL for call in calls):
        return
    pending_remote = [
        call
        for call in calls
        if call.execution_mode is ExecutionMode.REMOTE
        and call.status in {ToolCallStatus.PENDING, ToolCallStatus.RUNNING}
    ]
    if pending_remote and run.status is RunStatus.WAITING_FOR_APPROVAL:
        await uow.runs.transition(run_id, RunStatus.WAITING_FOR_TOOL)
        await uow.events.append(
            RunEvent(
                run_id=run_id,
                event_type=EventType.RUN_WAITING_FOR_TOOL,
                payload={"call_ids": [call.id for call in pending_remote]},
            )
        )
        return
    if all(call.status in _TERMINAL_TOOL_STATUSES for call in calls) and run.status in {
        RunStatus.WAITING_FOR_APPROVAL,
        RunStatus.WAITING_FOR_TOOL,
    }:
        await uow.runs.transition(run_id, RunStatus.QUEUED)
        await uow.events.append(
            RunEvent(
                run_id=run_id,
                event_type=EventType.RUN_REQUEUED,
                payload={"call_ids": [call.id for call in calls]},
            )
        )
