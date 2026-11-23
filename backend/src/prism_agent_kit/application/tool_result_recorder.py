"""工具结果的统一落库与事件发布，供引擎与审批服务共用。"""

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.ports import EventEnvelope, EventPublisher
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import ToolExecutionResult


class ToolResultRecorder:
    """把单次工具结果与其事件提交到数据库。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        event_publisher: EventPublisher,
    ) -> None:
        self._uow_factory = uow_factory
        self._event_publisher = event_publisher

    async def record(
        self,
        run_id: str,
        call_id: str,
        result: ToolExecutionResult,
    ) -> None:
        """成功写 tool 消息与完成事件，失败写错误内容与失败事件。"""
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            if result.ok:
                await uow.tool_calls.complete(run_id, call_id, result.output)
            else:
                if result.error_code is None:
                    raise AgentKitError(
                        ErrorCode.INTERNAL_ERROR,
                        "工具失败结果缺少错误码",
                        http_status=500,
                    )
                await uow.tool_calls.fail(
                    run_id,
                    call_id,
                    result.error_code,
                    result.error_message or "工具执行失败",
                )
            new_events = await uow.events.list_after(run_id, after_id=previous_event_id)
            await uow.commit()
        for event in new_events:
            await self._event_publisher.publish(
                EventEnvelope(
                    event_id=event.id,
                    run_id=event.run_id,
                    event_type=event.event_type,
                    payload=event.payload,
                    created_at=event.created_at,
                )
            )
