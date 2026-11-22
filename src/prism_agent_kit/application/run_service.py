from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import JsonValue

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.core.enums import EventType, MessageRole, RunStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run, RunEvent
from prism_agent_kit.core.ports import EventEnvelope, EventPublisher
from prism_agent_kit.core.prompts import Prompt, PromptRegistry
from prism_agent_kit.db.uow import UnitOfWorkFactory

_PROMPT_REQUEST_ERRORS = frozenset(
    {
        ErrorCode.PROMPT_NOT_FOUND,
        ErrorCode.INVALID_PROMPT_REF,
    }
)


class RunService:
    """管理 Run 创建与读取的应用服务。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        prompt_registry: PromptRegistry,
        model_name: str,
        default_prompt_ref: str,
        event_publisher: EventPublisher,
        cancellation_registry: RunCancellationRegistry,
    ) -> None:
        self._uow_factory = uow_factory
        self._prompt_registry = prompt_registry
        self._model_name = model_name
        self._default_prompt_ref = default_prompt_ref
        self._event_publisher = event_publisher
        self._cancellation_registry = cancellation_registry

    async def create(
        self,
        session_id: str,
        *,
        input_text: str,
        prompt_ref: str | None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> Run:
        """在单个事务中创建 user Message、Run 和排队事件。"""
        prompt = self._resolve_prompt(prompt_ref)
        async with self._uow_factory() as uow:
            await uow.sessions.get(session_id)
            run = await uow.runs.create(
                Run(
                    session_id=session_id,
                    input_text=input_text,
                    prompt_name=prompt.name,
                    prompt_version=prompt.version,
                    system_prompt=prompt.content,
                    model=self._model_name,
                )
            )
            await uow.messages.append(
                Message(
                    session_id=session_id,
                    run_id=run.id,
                    role=MessageRole.USER,
                    content=input_text,
                )
            )
            await uow.events.append(
                RunEvent(
                    run_id=run.id,
                    event_type=EventType.RUN_QUEUED,
                    payload=cast(
                        JsonValue,
                        {
                            "prompt_ref": prompt.ref,
                            "metadata": dict(metadata) if metadata is not None else {},
                        },
                    ),
                )
            )
            await uow.commit()
        return run

    async def get(self, run_id: str) -> Run:
        """读取指定 Run。"""
        async with self._uow_factory() as uow:
            return await uow.runs.get(run_id)

    async def list_events(
        self,
        run_id: str,
        *,
        after_event_id: int | None = None,
    ) -> list[RunEvent]:
        """读取指定 Run 游标之后的持久事件。"""
        async with self._uow_factory() as uow:
            await uow.runs.get(run_id)
            return await uow.events.list_after(run_id, after_event_id)

    async def cancel(self, run_id: str) -> Run:
        """取消 Run。running 由 Worker 在安全点收尾, 其余状态立即终止。"""
        events: list[RunEvent] = []
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            run = await uow.runs.get(run_id)
            if run.status in {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            }:
                return run

            cancel_signal = self._cancellation_registry.get(run_id)
            if cancel_signal is not None:
                cancel_signal.set()

            requested = await uow.runs.mark_cancel_requested(run_id)
            if run.status is RunStatus.RUNNING and cancel_signal is not None:
                await uow.commit()
                return requested

            await uow.tool_calls.close_open_calls(
                run_id,
                ErrorCode.RUN_CANCELLED,
                "Run 已取消",
            )
            cancelled = await uow.runs.transition(
                run_id,
                RunStatus.CANCELLED,
                error_code=ErrorCode.RUN_CANCELLED.value,
                error_message="Run 已取消",
            )
            await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.RUN_CANCELLED,
                    payload={},
                )
            )
            events = await uow.events.list_after(
                run_id,
                after_id=previous_event_id,
            )
            await uow.commit()

        await self._publish_events(events)
        return cancelled

    async def _publish_events(self, events: Sequence[RunEvent]) -> None:
        """事务提交后发布取消相关事件。"""
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

    def _resolve_prompt(self, prompt_ref: str | None) -> Prompt:
        """解析显式 Prompt 引用。查找失败按请求参数错误映射为 422。"""
        resolved_ref = prompt_ref or self._default_prompt_ref
        try:
            return self._prompt_registry.get_by_ref(resolved_ref)
        except AgentKitError as error:
            if error.code not in _PROMPT_REQUEST_ERRORS:
                raise
            raise AgentKitError(
                error.code,
                error.message,
                http_status=422,
                details=error.details,
            ) from error
