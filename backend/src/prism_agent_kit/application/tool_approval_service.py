"""写入审批服务：生成预览、执行已批准的工具并闭合轮次。"""

from __future__ import annotations

import asyncio
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.tool_result_recorder import ToolResultRecorder
from prism_agent_kit.core.enums import EventType, ExecutionMode, RunStatus, ToolCallStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import RunEvent, ToolCall, utc_now
from prism_agent_kit.core.ports import EventEnvelope, EventPublisher
from prism_agent_kit.core.workspace_paths import resolve_in_workspace
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolExecutionContext
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry

_TERMINAL_TOOL_STATUSES = frozenset(
    {
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
        ToolCallStatus.EXPIRED,
        ToolCallStatus.CANCELLED,
    }
)


@dataclass(frozen=True)
class ApprovalPreview:
    """写入审批的展示信息。"""

    path: str
    mode: str
    bytes: int
    exists: bool
    diff: str | None
    truncated: bool


def _diff_text(old: str, new: str, *, path: str) -> tuple[str, bool]:
    """生成行级统一 diff，最多 200 行、20 KB。"""
    lines = list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=path,
            tofile=path,
            lineterm="",
            n=3,
        )
    )
    truncated = len(lines) > 200
    text = "\n".join(lines[:200])
    if len(text) > 20_000:
        text = text[:20_000]
        truncated = True
    return text, truncated


class ToolApprovalService:
    """审批决策与执行。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        tool_registry: ToolRegistry,
        tool_executor: LocalToolExecutor,
        tool_result_recorder: ToolResultRecorder,
        workspace_service: Any,
        index_tasks: Any,
        event_publisher: EventPublisher,
        cancellation_registry: RunCancellationRegistry,
    ) -> None:
        self._uow_factory = uow_factory
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._recorder = tool_result_recorder
        self._workspace_service = workspace_service
        self._index_tasks = index_tasks
        self._event_publisher = event_publisher
        self._cancellation_registry = cancellation_registry
        self._lock = asyncio.Lock()

    async def preview(self, run_id: str, call_id: str) -> ApprovalPreview:
        """为待审批写入生成路径、存在性与 diff 预览。"""
        async with self._uow_factory() as uow:
            run = await uow.runs.get(run_id)
            call = await uow.tool_calls.get(run_id, call_id)
        if call.status is not ToolCallStatus.AWAITING_APPROVAL:
            raise AgentKitError(
                ErrorCode.RUN_CONFLICT,
                "工具调用不处于待审批状态",
                http_status=409,
                details={"call_id": call_id, "status": call.status.value},
            )
        data = call.input if isinstance(call.input, dict) else {}
        rel_path = str(data.get("path", ""))
        mode = str(data.get("mode", "overwrite"))
        content = data.get("content")
        text = content if isinstance(content, str) else ""
        root = await self._workspace_service.root_for(run.workspace_id)
        if root is None:
            raise AgentKitError(
                ErrorCode.WORKSPACE_NOT_BOUND,
                "Run 绑定的工作区不存在",
                http_status=409,
            )
        target = resolve_in_workspace(root, rel_path)
        return await asyncio.to_thread(self._build_preview, target, rel_path, mode, text)

    async def decide(
        self,
        run_id: str,
        call_id: str,
        decision: str,
        reason: str | None = None,
    ) -> tuple[ToolCall, Any]:
        """批准或拒绝一次写入，并在轮次闭合后决定 Run 去向。"""
        if decision not in {"approve", "reject"}:
            raise AgentKitError(
                ErrorCode.INVALID_REQUEST,
                "decision 只能是 approve 或 reject",
                http_status=422,
            )
        async with self._lock:
            async with self._uow_factory() as uow:
                run = await uow.runs.get(run_id)
                call = await uow.tool_calls.get(run_id, call_id)

            if call.status in _TERMINAL_TOOL_STATUSES:
                return await self._idempotent_result(run_id, call_id, decision)
            if call.status is not ToolCallStatus.AWAITING_APPROVAL:
                raise AgentKitError(
                    ErrorCode.RUN_CONFLICT,
                    "工具调用不处于待审批状态",
                    http_status=409,
                    details={"call_id": call_id, "status": call.status.value},
                )
            if call.expires_at is not None and utc_now() >= call.expires_at:
                raise AgentKitError(
                    ErrorCode.TOOL_CALL_EXPIRED,
                    "审批已超时",
                    http_status=409,
                    details={"call_id": call_id},
                )

            if decision == "reject":
                await self._reject(run_id, call_id, reason)
                await self._finalize(run_id)
                return await self._load(run_id, call_id)

            definition = self._tool_registry.get(call.tool_name)
            workspace_root = await self._workspace_service.root_for(run.workspace_id)
            if workspace_root is None:
                await self._reject(run_id, call_id, "Run 绑定的工作区不存在")
                await self._finalize(run_id)
                return await self._load(run_id, call_id)
            await self._mark_running(run_id, call_id)

        cancel = self._cancellation_registry.register(run_id)
        try:
            result = await self._tool_executor.execute(
                definition,
                call.input,
                ToolExecutionContext(
                    run_id=run_id,
                    session_id=run.session_id,
                    call_id=call_id,
                    cancel=cancel,
                    workspace_root=workspace_root,
                    workspace_id=run.workspace_id,
                    search=self._search_callback(run.workspace_id),
                ),
            )
        finally:
            self._cancellation_registry.unregister(run_id)

        await self._recorder.record(run_id, call_id, result)

        if result.ok:
            rel_path = cast(dict[str, Any], call.input if isinstance(call.input, dict) else {}).get(
                "path"
            )
            if run.workspace_id is not None and isinstance(rel_path, str):
                await self._index_tasks.submit(run.workspace_id, mode="file", rel_path=rel_path)
        if result.error_code is ErrorCode.RUN_CANCELLED:
            await self._cancel_run(run_id)
            return await self._load(run_id, call_id)

        await self._finalize(run_id)
        return await self._load(run_id, call_id)

    def _search_callback(self, workspace_id: str | None) -> Any:
        if workspace_id is None:
            return None

        async def search(query: str, limit: int) -> list[object]:
            results = await self._workspace_service.search(workspace_id, query, limit=limit)
            return [item for item in results]

        return search

    def _build_preview(
        self,
        target: Path,
        rel_path: str,
        mode: str,
        content: str,
    ) -> ApprovalPreview:
        exists = target.is_file()
        if not exists or mode == "append":
            return ApprovalPreview(
                path=rel_path,
                mode=mode,
                bytes=len(content.encode("utf-8")),
                exists=exists,
                diff=None,
                truncated=False,
            )
        old = target.read_text(encoding="utf-8", errors="replace")
        diff, truncated = _diff_text(old, content, path=rel_path)
        return ApprovalPreview(
            path=rel_path,
            mode=mode,
            bytes=len(content.encode("utf-8")),
            exists=True,
            diff=diff,
            truncated=truncated,
        )

    async def _idempotent_result(
        self, run_id: str, call_id: str, decision: str
    ) -> tuple[ToolCall, Any]:
        """终态调用的重复审批：相同结论按幂等返回，其余冲突。"""
        async with self._uow_factory() as uow:
            call = await uow.tool_calls.get(run_id, call_id)
            run = await uow.runs.get(run_id)
        if decision == "approve" and call.status is ToolCallStatus.SUCCEEDED:
            return call, run
        if (
            decision == "reject"
            and call.status is ToolCallStatus.FAILED
            and call.error_code == ErrorCode.TOOL_REJECTED.value
        ):
            return call, run
        raise AgentKitError(
            ErrorCode.RUN_CONFLICT,
            "工具调用已由其他结论闭合",
            http_status=409,
            details={"call_id": call_id, "status": call.status.value},
        )

    async def _reject(self, run_id: str, call_id: str, reason: str | None) -> None:
        message = reason or "用户拒绝写入"
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            await uow.tool_calls.fail(run_id, call_id, ErrorCode.TOOL_REJECTED, message)
            await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.TOOL_REJECTED,
                    payload={"call_id": call_id, "reason": message},
                )
            )
            new_events = await uow.events.list_after(run_id, after_id=previous_event_id)
            await uow.commit()
        await self._publish(new_events)

    async def _mark_running(self, run_id: str, call_id: str) -> None:
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            await uow.tool_calls.start_after_approval(run_id, call_id)
            await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.TOOL_APPROVED,
                    payload={"call_id": call_id},
                )
            )
            new_events = await uow.events.list_after(run_id, after_id=previous_event_id)
            await uow.commit()
        await self._publish(new_events)

    async def _finalize(self, run_id: str) -> None:
        """根据全部调用状态决定 Run 的去向。"""
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            run = await uow.runs.get(run_id)
            calls = await uow.tool_calls.list_for_run(run_id)
            if any(call.status is ToolCallStatus.AWAITING_APPROVAL for call in calls):
                await uow.commit()
                return
            pending_remote = any(
                call.execution_mode is ExecutionMode.REMOTE
                and call.status in {ToolCallStatus.PENDING, ToolCallStatus.RUNNING}
                for call in calls
            )
            if pending_remote and run.status is RunStatus.WAITING_FOR_APPROVAL:
                await uow.runs.transition(run_id, RunStatus.WAITING_FOR_TOOL)
                await uow.events.append(
                    RunEvent(
                        run_id=run_id,
                        event_type=EventType.RUN_WAITING_FOR_TOOL,
                        payload={
                            "call_ids": [
                                call.id
                                for call in calls
                                if call.execution_mode is ExecutionMode.REMOTE
                                and call.status in {ToolCallStatus.PENDING, ToolCallStatus.RUNNING}
                            ]
                        },
                    )
                )
            elif (
                all(call.status in _TERMINAL_TOOL_STATUSES for call in calls)
                and run.status is RunStatus.WAITING_FOR_APPROVAL
            ):
                await uow.runs.transition(run_id, RunStatus.QUEUED)
                await uow.events.append(
                    RunEvent(
                        run_id=run_id,
                        event_type=EventType.RUN_REQUEUED,
                        payload={"call_ids": [call.id for call in calls]},
                    )
                )
            new_events = await uow.events.list_after(run_id, after_id=previous_event_id)
            await uow.commit()
        await self._publish(new_events)

    async def _cancel_run(self, run_id: str) -> None:
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            await uow.tool_calls.close_open_calls(run_id, ErrorCode.RUN_CANCELLED, "Run 已取消")
            run = await uow.runs.get(run_id)
            if run.status is not RunStatus.CANCELLED:
                await uow.runs.transition(run_id, RunStatus.CANCELLED)
            await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.RUN_CANCELLED,
                    payload={},
                )
            )
            new_events = await uow.events.list_after(run_id, after_id=previous_event_id)
            await uow.commit()
        await self._publish(new_events)

    async def _load(self, run_id: str, call_id: str) -> tuple[ToolCall, Any]:
        async with self._uow_factory() as uow:
            call = await uow.tool_calls.get(run_id, call_id)
            run = await uow.runs.get(run_id)
        return call, run

    async def _publish(self, events: list[RunEvent]) -> None:
        for event in events:
            await self._event_publisher.publish(
                EventEnvelope(
                    event_id=event.id,
                    run_id=event.run_id,
                    event_type=event.event_type,
                    payload=event.payload,
                    created_at=event.created_at,
                )
            )
