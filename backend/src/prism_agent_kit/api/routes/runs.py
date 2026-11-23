import json
from collections.abc import AsyncIterator, Iterable
from typing import Annotated, cast

from fastapi import APIRouter, Header
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from prism_agent_kit.api.dependencies import (
    EventBusDependency,
    RunServiceDependency,
    SettingsDependency,
    ToolApprovalServiceDependency,
    ToolResultServiceDependency,
)
from prism_agent_kit.api.schemas import (
    ApprovalPreviewView,
    ApprovalRequest,
    ApprovalResponse,
    RunCreate,
    RunView,
    ToolCallView,
    ToolResultRequest,
)
from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.application.tool_result_service import (
    RemoteToolError,
    RemoteToolResult,
)
from prism_agent_kit.core.enums import EventType, RunStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import RunEvent
from prism_agent_kit.core.ports import EventEnvelope

_TERMINAL_EVENT_TYPES = frozenset(
    {
        EventType.RUN_SUCCEEDED,
        EventType.RUN_FAILED,
        EventType.RUN_CANCELLED,
    }
)
_TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }
)


def _serialize_event(event: EventEnvelope) -> ServerSentEvent:
    """把统一事件信封编码为 SSE 事件。"""
    data: dict[str, object] = {
        "type": event.event_type.value,
        "run_id": event.run_id,
    }
    if isinstance(event.payload, dict):
        data.update(cast(dict[str, object], event.payload))
    else:
        data["payload"] = event.payload

    return ServerSentEvent(
        event=event.event_type.value,
        id=str(event.event_id) if event.event_id is not None else None,
        data=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    )


async def iter_run_events(
    event_bus: RunEventBus,
    run_id: str,
    after_event_id: int | None,
) -> AsyncIterator[ServerSentEvent]:
    """订阅实时事件并在持久终态事件后关闭。"""
    async for event in event_bus.subscribe(run_id, after_event_id):
        yield _serialize_event(event)
        if event.event_type in _TERMINAL_EVENT_TYPES:
            return


async def _iter_replayed_events(events: Iterable[RunEvent]) -> AsyncIterator[ServerSentEvent]:
    """有界重放持久事件。测试模式使用。"""
    for event in events:
        yield _serialize_event(
            EventEnvelope(
                event_id=event.id,
                run_id=event.run_id,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
        )
        if event.event_type in _TERMINAL_EVENT_TYPES:
            return


def _parse_after_event_id(value: str | None) -> int | None:
    """解析 Last-Event-ID。非法游标作为请求错误拒绝。"""
    if value is None:
        return None
    try:
        after_event_id = int(value)
    except ValueError as error:
        raise AgentKitError(
            ErrorCode.INVALID_REQUEST,
            "Last-Event-ID 必须是整数",
            http_status=400,
        ) from error
    if after_event_id < 0:
        raise AgentKitError(
            ErrorCode.INVALID_REQUEST,
            "Last-Event-ID 不能为负数",
            http_status=400,
        )
    return after_event_id


def create_runs_router() -> APIRouter:
    """创建 Run 相关路由。"""
    router = APIRouter(tags=["runs"])

    @router.post(
        "/sessions/{session_id}/runs",
        response_model=RunView,
        status_code=202,
        summary="创建 Run",
    )
    async def create_run(
        session_id: str,
        payload: RunCreate,
        service: RunServiceDependency,
    ) -> RunView:
        run = await service.create(
            session_id,
            input_text=payload.input,
            prompt_ref=payload.prompt_ref,
            metadata=payload.metadata,
        )
        return RunView.from_domain(run)

    @router.get("/runs/{run_id}", response_model=RunView, summary="获取 Run")
    async def get_run(run_id: str, service: RunServiceDependency) -> RunView:
        run = await service.get(run_id)
        return RunView.from_domain(run)

    @router.post("/runs/{run_id}/cancel", response_model=RunView, summary="取消 Run")
    async def cancel_run(run_id: str, service: RunServiceDependency) -> RunView:
        run = await service.cancel(run_id)
        return RunView.from_domain(run)

    @router.post(
        "/runs/{run_id}/tool-calls/{call_id}/result",
        response_model=ToolCallView,
        summary="提交远端工具结果",
    )
    async def submit_tool_result(
        run_id: str,
        call_id: str,
        payload: ToolResultRequest,
        tool_result_service: ToolResultServiceDependency,
    ) -> ToolCallView:
        error = (
            RemoteToolError(
                code=payload.error.code,
                message=payload.error.message,
            )
            if payload.error is not None
            else None
        )
        call = await tool_result_service.submit(
            run_id,
            call_id,
            payload.input_digest,
            RemoteToolResult(
                ok=payload.ok,
                output=payload.output,
                error=error,
            ),
        )
        return ToolCallView.from_domain(call)

    @router.get(
        "/runs/{run_id}/tool-calls/{call_id}/preview",
        response_model=ApprovalPreviewView,
        summary="获取写入预览",
    )
    async def preview_tool_call(
        run_id: str,
        call_id: str,
        service: ToolApprovalServiceDependency,
    ) -> ApprovalPreviewView:
        preview = await service.preview(run_id, call_id)
        return ApprovalPreviewView(
            path=preview.path,
            mode=preview.mode,
            bytes=preview.bytes,
            exists=preview.exists,
            diff=preview.diff,
            truncated=preview.truncated,
        )

    @router.post(
        "/runs/{run_id}/tool-calls/{call_id}/approval",
        response_model=ApprovalResponse,
        summary="审批写入",
    )
    async def decide_approval(
        run_id: str,
        call_id: str,
        payload: ApprovalRequest,
        service: ToolApprovalServiceDependency,
    ) -> ApprovalResponse:
        call, run = await service.decide(run_id, call_id, payload.decision, payload.reason)
        return ApprovalResponse(
            call=ToolCallView.from_domain(call),
            run=RunView.from_domain(run),
        )

    @router.get("/runs/{run_id}/events", summary="订阅 Run 事件流")
    async def stream_run_events(
        run_id: str,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
        once: bool = False,
        *,
        service: RunServiceDependency,
        event_bus: EventBusDependency,
        settings: SettingsDependency,
    ) -> EventSourceResponse:
        run = await service.get(run_id)
        after_event_id = _parse_after_event_id(last_event_id)

        # 终态 Run 不会再有新事件。有限重放避免客户端重连后永久挂起。
        if run.status in _TERMINAL_RUN_STATUSES:
            events = await service.list_events(
                run_id,
                after_event_id=after_event_id,
            )
            return EventSourceResponse(
                _iter_replayed_events(events),
                ping=settings.sse_heartbeat_seconds,
            )

        if once:
            if settings.environment != "test":
                raise AgentKitError(
                    ErrorCode.INVALID_REQUEST,
                    "once 参数仅在测试环境可用",
                    http_status=400,
                )
            events = await service.list_events(
                run_id,
                after_event_id=after_event_id,
            )
            return EventSourceResponse(
                _iter_replayed_events(events),
                ping=settings.sse_heartbeat_seconds,
            )

        return EventSourceResponse(
            iter_run_events(event_bus, run_id, after_event_id),
            ping=settings.sse_heartbeat_seconds,
        )

    return router
