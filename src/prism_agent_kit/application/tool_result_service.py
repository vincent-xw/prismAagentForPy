import json
from typing import cast

from pydantic import BaseModel, JsonValue, ValidationError

from prism_agent_kit.core.enums import (
    EventType,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import RunEvent, ToolCall, utc_now
from prism_agent_kit.core.ports import EventEnvelope, EventPublisher
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.registry import ToolRegistry

_TERMINAL_TOOL_STATUSES = frozenset(
    {
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
        ToolCallStatus.EXPIRED,
        ToolCallStatus.CANCELLED,
    }
)


class RemoteToolError(BaseModel):
    """远端宿主返回的工具错误。"""

    code: str
    message: str


class RemoteToolResult(BaseModel):
    """远端宿主回填结果的统一载荷。"""

    ok: bool
    output: JsonValue = None
    error: RemoteToolError | None = None


class ToolResultService:
    """校验并原子提交远端工具结果。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        tool_registry: ToolRegistry,
        event_publisher: EventPublisher,
    ) -> None:
        self._uow_factory = uow_factory
        self._tool_registry = tool_registry
        self._event_publisher = event_publisher

    async def submit(
        self,
        run_id: str,
        call_id: str,
        input_digest: str,
        result: RemoteToolResult,
    ) -> ToolCall:
        """校验 Run、摘要、过期时间与输出 Schema 后提交结果。"""
        events: list[RunEvent] = []
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            run = await uow.runs.get(run_id)
            call = await uow.tool_calls.get(run_id, call_id)

            if call.input_digest != input_digest:
                raise AgentKitError(
                    ErrorCode.TOOL_RESULT_CONFLICT,
                    "工具输入摘要不匹配",
                    http_status=409,
                    details={"call_id": call_id},
                )

            terminal = call.status in _TERMINAL_TOOL_STATUSES
            if not terminal:
                if run.status is not RunStatus.WAITING_FOR_TOOL:
                    raise AgentKitError(
                        ErrorCode.RUN_CONFLICT,
                        "Run 未处于等待远端工具状态",
                        http_status=409,
                        details={"run_id": run_id, "status": run.status.value},
                    )
                if call.expires_at is not None and utc_now() >= call.expires_at:
                    raise AgentKitError(
                        ErrorCode.TOOL_CALL_EXPIRED,
                        "ToolCall 已过期",
                        http_status=409,
                        details={"call_id": call_id},
                    )

            if result.ok:
                output = self._validate_output(call.tool_name, result.output)
                await uow.tool_calls.complete(run_id, call_id, output)
            else:
                if terminal:
                    raise AgentKitError(
                        ErrorCode.TOOL_RESULT_CONFLICT,
                        "ToolCall 已由其他结果闭合",
                        http_status=409,
                        details={"call_id": call_id},
                    )
                if result.error is None:
                    raise AgentKitError(
                        ErrorCode.INVALID_REQUEST,
                        "失败结果必须提供 error",
                        http_status=422,
                        details={"call_id": call_id},
                    )
                if not result.error.code or not result.error.message:
                    raise AgentKitError(
                        ErrorCode.INVALID_REQUEST,
                        "工具错误码与消息不能为空",
                        http_status=422,
                        details={"call_id": call_id},
                    )
                await uow.tool_calls.fail(
                    run_id,
                    call_id,
                    result.error.code,
                    result.error.message,
                )

            refreshed_run = await uow.runs.get(run_id)
            calls = await uow.tool_calls.list_for_run(run_id)
            if refreshed_run.status is RunStatus.WAITING_FOR_TOOL and all(
                item.status in _TERMINAL_TOOL_STATUSES for item in calls
            ):
                await uow.runs.transition(run_id, RunStatus.QUEUED)
                await uow.events.append(
                    RunEvent(
                        run_id=run_id,
                        event_type=EventType.RUN_REQUEUED,
                        payload={"call_ids": cast(JsonValue, [item.id for item in calls])},
                    )
                )

            updated = await uow.tool_calls.get(run_id, call_id)
            events = await uow.events.list_after(
                run_id,
                after_id=previous_event_id,
            )
            await uow.commit()

        await self._publish_events(events)
        return updated

    def _validate_output(self, tool_name: str, output: JsonValue) -> JsonValue:
        """使用工具输出 Schema 校验宿主回填结果。"""
        definition = self._tool_registry.get(tool_name)
        if definition.output_model is not None:
            try:
                validated = definition.output_model.model_validate(output)
            except ValidationError as error:
                raise AgentKitError(
                    ErrorCode.TOOL_OUTPUT_INVALID,
                    "工具输出不符合 Schema",
                    http_status=422,
                    details={"tool_name": tool_name},
                ) from error
            return cast(JsonValue, validated.model_dump(mode="json"))
        try:
            serialized = json.dumps(output, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise AgentKitError(
                ErrorCode.TOOL_OUTPUT_INVALID,
                "工具输出不是合法 JSON",
                http_status=422,
                details={"tool_name": tool_name},
            ) from error
        return cast(JsonValue, json.loads(serialized))

    async def _publish_events(self, events: list[RunEvent]) -> None:
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
