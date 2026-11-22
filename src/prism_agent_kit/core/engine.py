import asyncio
import logging
from datetime import timedelta
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy.exc import IntegrityError

from prism_agent_kit.core.context import ContextAssembler, ContextAssembly
from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    MessageRole,
    RunStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run, RunEvent, ToolCall, utc_now
from prism_agent_kit.core.ports import (
    EventEnvelope,
    EventPublisher,
    ModelChunk,
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.contracts import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_CONTRACT_ERROR_CODES = frozenset(
    {
        ErrorCode.TOOL_INPUT_INVALID,
        ErrorCode.TOOL_OUTPUT_INVALID,
        ErrorCode.INVALID_TOOL_DEFINITION,
    }
)
_TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }
)


class EngineContext(BaseModel):
    """单次引擎执行所需的 Run ID 与协作式取消信号。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    cancel: asyncio.Event


class EngineOutcome(BaseModel):
    """引擎执行结果。不把可恢复失败抛给 Worker。"""

    kind: Literal["completed", "waiting_for_tools", "failed", "cancelled"]
    error_code: ErrorCode | None = None
    message: str | None = None


class AgentEngine(Protocol):
    """可替换 Agent Runtime 的稳定接口。"""

    async def execute(self, context: EngineContext) -> EngineOutcome: ...

    async def resume(self, context: EngineContext) -> EngineOutcome: ...

    async def cancel(self, run_id: str) -> EngineOutcome: ...


class SimpleAgentEngine:
    """首版自研模型与工具循环。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        model_provider: ModelProvider,
        tool_registry: ToolRegistry,
        tool_executor: LocalToolExecutor,
        context_assembler: ContextAssembler,
        event_publisher: EventPublisher,
        max_steps: int,
        max_output_tokens: int | None,
        remote_tool_timeout_seconds: float,
    ) -> None:
        self._uow_factory = uow_factory
        self._model_provider = model_provider
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._context_assembler = context_assembler
        self._event_publisher = event_publisher
        self._max_steps = max_steps
        self._max_output_tokens = max_output_tokens
        self._remote_tool_timeout_seconds = remote_tool_timeout_seconds

    async def execute(self, context: EngineContext) -> EngineOutcome:
        """执行一次已 claim 的 Run。"""
        return await self._run(context)

    async def resume(self, context: EngineContext) -> EngineOutcome:
        """从已持久化历史继续执行 Run。不重新执行旧工具调用。"""
        return await self._run(context)

    async def cancel(self, run_id: str) -> EngineOutcome:
        """取消 Run 并闭合全部未完成工具调用。"""
        return await self._cancel_run(run_id)

    async def _run(self, context: EngineContext) -> EngineOutcome:
        run = await self._load_run(context.run_id)
        if run.status is not RunStatus.RUNNING:
            raise AgentKitError(
                ErrorCode.INVALID_RUN_TRANSITION,
                "只有 running Run 可以进入引擎",
                http_status=409,
                details={"run_id": run.id, "status": run.status.value},
            )
        if context.cancel.is_set():
            return await self._cancel_run(run.id)

        await self._emit_started(run.id)
        tool_schemas = self._tool_registry.model_schemas()

        while True:
            if context.cancel.is_set():
                return await self._cancel_run(run.id)

            async with self._uow_factory() as uow:
                current = await uow.runs.get(run.id)
                step_count = current.step_count
                messages = await uow.messages.list_for_session(current.session_id)
                history_calls = await uow.tool_calls.list_for_session(current.session_id)

            if step_count >= self._max_steps:
                return await self._fail_run(
                    run.id,
                    ErrorCode.HARNESS_STEP_LIMIT,
                    "Run 已达到最大模型步数",
                )

            try:
                assembly = self._context_assembler.assemble(
                    system_prompt=current.system_prompt,
                    messages=messages,
                    tool_calls=history_calls,
                    tool_schemas=tool_schemas,
                )
            except AgentKitError as error:
                return await self._fail_run(run.id, error.code, error.message)

            try:
                response = await self._model_provider.stream(
                    ModelRequest(
                        system_prompt=current.system_prompt,
                        messages=assembly.messages,
                        tool_calls=history_calls,
                        tools=tool_schemas,
                        max_output_tokens=self._max_output_tokens,
                    ),
                    on_delta=lambda chunk: self._publish_delta(run.id, chunk),
                )
            except asyncio.CancelledError:
                raise
            except AgentKitError as error:
                return await self._fail_run(run.id, error.code, error.message)

            try:
                definitions = self._resolve_tool_definitions(response)
            except AgentKitError as error:
                return await self._fail_run(run.id, error.code, error.message)

            outcome, calls, ordered_definitions = await self._persist_model_turn(
                run.id,
                current.session_id,
                response,
                definitions,
                assembly,
            )
            if outcome is not None:
                return outcome

            for call, definition in zip(
                calls,
                ordered_definitions,
                strict=True,
            ):
                if definition.execution_mode is ExecutionMode.REMOTE:
                    continue
                if context.cancel.is_set():
                    return await self._cancel_run(run.id)
                async with self._uow_factory() as uow:
                    await uow.tool_calls.start(run.id, call.id)
                    await uow.commit()

                result = await self._tool_executor.execute(
                    definition,
                    call.input,
                    ToolExecutionContext(
                        run_id=run.id,
                        session_id=current.session_id,
                        call_id=call.id,
                        cancel=context.cancel,
                    ),
                )
                if result.error_code is ErrorCode.RUN_CANCELLED:
                    return await self._cancel_run(run.id)
                if result.error_code in _CONTRACT_ERROR_CODES:
                    return await self._fail_after_contract(
                        run.id,
                        call.id,
                        result,
                    )
                await self._record_tool_result(run.id, call.id, result)

            if any(
                definition.execution_mode is ExecutionMode.REMOTE
                for definition in ordered_definitions
            ):
                return await self._wait_for_remote_tools(
                    run.id,
                    [
                        call.id
                        for call, definition in zip(
                            calls,
                            ordered_definitions,
                            strict=True,
                        )
                        if definition.execution_mode is ExecutionMode.REMOTE
                    ],
                )

    async def _persist_model_turn(
        self,
        run_id: str,
        session_id: str,
        response: ModelResponse,
        definitions: dict[str, ToolDefinition],
        assembly: ContextAssembly,
    ) -> tuple[EngineOutcome | None, list[ToolCall], list[ToolDefinition]]:
        """持久化 assistant 与全部 ToolCall。无工具时直接完成 Run。"""
        persisted_events: list[RunEvent] = []
        try:
            async with self._uow_factory() as uow:
                run = await uow.runs.get(run_id)
                assistant = await uow.messages.append(
                    Message(
                        session_id=session_id,
                        run_id=run_id,
                        role=MessageRole.ASSISTANT,
                        content=response.text,
                        reasoning=response.reasoning,
                    )
                )
                if assistant.id is None:
                    raise RuntimeError("assistant Message 未获得数据库 ID")

                calls = [
                    ToolCall(
                        id=draft.call_id,
                        run_id=run_id,
                        assistant_message_id=assistant.id,
                        tool_name=draft.tool_name,
                        execution_mode=definitions[draft.call_id].execution_mode,
                        input=draft.input,
                        input_digest=canonical_json_digest(draft.input),
                        expires_at=(
                            utc_now() + timedelta(seconds=self._remote_tool_timeout_seconds)
                            if definitions[draft.call_id].execution_mode is ExecutionMode.REMOTE
                            else None
                        ),
                    )
                    for draft in response.tool_calls
                ]
                if calls:
                    await uow.tool_calls.create_many(calls)

                await uow.runs.update_step_count(run_id, run.step_count + 1)
                persisted_events.append(
                    await uow.events.append(
                        RunEvent(
                            run_id=run_id,
                            event_type=EventType.ASSISTANT_COMPLETED,
                            payload={
                                "message_id": assistant.id,
                                "tool_call_ids": [call.id for call in calls],
                            },
                        )
                    )
                )
                for call in calls:
                    persisted_events.append(
                        await uow.events.append(
                            RunEvent(
                                run_id=run_id,
                                event_type=EventType.TOOL_REQUESTED,
                                payload={
                                    "call_id": call.id,
                                    "tool_name": call.tool_name,
                                    "execution_mode": call.execution_mode.value,
                                    "input": call.input,
                                    "input_digest": call.input_digest,
                                },
                            )
                        )
                    )
                if assembly.trimmed_count > 0:
                    persisted_events.append(
                        await uow.events.append(
                            RunEvent(
                                run_id=run_id,
                                event_type=EventType.CONTEXT_TRIMMED,
                                payload={
                                    "trimmed_count": assembly.trimmed_count,
                                    "trimmed_tokens": assembly.trimmed_tokens,
                                },
                            )
                        )
                    )

                completed = not calls
                if completed:
                    await uow.runs.transition(
                        run_id,
                        RunStatus.SUCCEEDED,
                        output_text=response.text,
                    )
                    persisted_events.append(
                        await uow.events.append(
                            RunEvent(
                                run_id=run_id,
                                event_type=EventType.RUN_SUCCEEDED,
                                payload={"message_id": assistant.id},
                            )
                        )
                    )
                await uow.commit()
        except IntegrityError:
            outcome = await self._fail_run(
                run_id,
                ErrorCode.MODEL_PROTOCOL_INVALID,
                "模型返回了重复的工具调用 ID",
            )
            return outcome, [], []

        await self._publish_events(persisted_events)
        if not calls:
            return EngineOutcome(kind="completed"), [], []
        return (
            None,
            calls,
            [definitions[call.id] for call in calls],
        )

    def _resolve_tool_definitions(
        self,
        response: ModelResponse,
    ) -> dict[str, ToolDefinition]:
        """在写库前解析全部工具。未知或重复工具直接失败。"""
        definitions: dict[str, ToolDefinition] = {}
        for draft in response.tool_calls:
            if draft.call_id in definitions:
                raise AgentKitError(
                    ErrorCode.MODEL_PROTOCOL_INVALID,
                    "模型返回了重复的工具调用 ID",
                    http_status=502,
                    details={"call_id": draft.call_id},
                )
            definitions[draft.call_id] = self._tool_registry.get(draft.tool_name)
        return definitions

    async def _record_tool_result(
        self,
        run_id: str,
        call_id: str,
        result: ToolExecutionResult,
    ) -> None:
        """把单次本地工具结果与其事件提交到数据库。"""
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
            new_events = await uow.events.list_after(
                run_id,
                after_id=previous_event_id,
            )
            await uow.commit()
        await self._publish_events(new_events)

    async def _fail_after_contract(
        self,
        run_id: str,
        call_id: str,
        result: ToolExecutionResult,
    ) -> EngineOutcome:
        """工具契约失败时把 Run 置为失败并闭合同轮其他调用。"""
        error_code = result.error_code or ErrorCode.INTERNAL_ERROR
        message = result.error_message or "工具契约失败"
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            await uow.tool_calls.fail(run_id, call_id, error_code, message)
            await uow.tool_calls.close_open_calls(
                run_id,
                ErrorCode.TOOL_EXECUTION_FAILED,
                "同一轮其他工具因契约失败未执行",
            )
            await uow.runs.transition(
                run_id,
                RunStatus.FAILED,
                error_code=error_code.value,
                error_message=message,
            )
            await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.RUN_FAILED,
                    payload={
                        "error_code": error_code.value,
                        "error_message": message,
                    },
                )
            )
            new_events = await uow.events.list_after(
                run_id,
                after_id=previous_event_id,
            )
            await uow.commit()
        await self._publish_events(new_events)
        return EngineOutcome(kind="failed", error_code=error_code, message=message)

    async def _wait_for_remote_tools(
        self,
        run_id: str,
        call_ids: list[str],
    ) -> EngineOutcome:
        """进入 waiting_for_tool 等待宿主回填全部远端结果。"""
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            await uow.runs.transition(run_id, RunStatus.WAITING_FOR_TOOL)
            await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.RUN_WAITING_FOR_TOOL,
                    payload={"call_ids": cast(JsonValue, call_ids)},
                )
            )
            new_events = await uow.events.list_after(
                run_id,
                after_id=previous_event_id,
            )
            await uow.commit()
        await self._publish_events(new_events)
        return EngineOutcome(kind="waiting_for_tools")

    async def _fail_run(
        self,
        run_id: str,
        error_code: ErrorCode,
        message: str,
    ) -> EngineOutcome:
        """在单个终态事务中闭合工具调用并标记 Run 失败。"""
        async with self._uow_factory() as uow:
            run = await uow.runs.get(run_id)
            previous_event_id = await uow.events.last_id(run_id)
            if run.status not in _TERMINAL_RUN_STATUSES:
                await uow.tool_calls.close_open_calls(run_id, error_code, message)
                await uow.runs.transition(
                    run_id,
                    RunStatus.FAILED,
                    error_code=error_code.value,
                    error_message=message,
                )
                await uow.events.append(
                    RunEvent(
                        run_id=run_id,
                        event_type=EventType.RUN_FAILED,
                        payload={
                            "error_code": error_code.value,
                            "error_message": message,
                        },
                    )
                )
            new_events = await uow.events.list_after(
                run_id,
                after_id=previous_event_id,
            )
            await uow.commit()
        await self._publish_events(new_events)
        return EngineOutcome(kind="failed", error_code=error_code, message=message)

    async def _cancel_run(self, run_id: str) -> EngineOutcome:
        """协作式取消 Run 并闭合全部未完成工具调用。"""
        async with self._uow_factory() as uow:
            run = await uow.runs.get(run_id)
            previous_event_id = await uow.events.last_id(run_id)
            if run.status not in _TERMINAL_RUN_STATUSES:
                await uow.tool_calls.close_open_calls(
                    run_id,
                    ErrorCode.RUN_CANCELLED,
                    "Run 已取消",
                )
                await uow.runs.transition(
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
            new_events = await uow.events.list_after(
                run_id,
                after_id=previous_event_id,
            )
            await uow.commit()
        await self._publish_events(new_events)
        return EngineOutcome(kind="cancelled", error_code=ErrorCode.RUN_CANCELLED)

    async def _emit_started(self, run_id: str) -> None:
        """每个 Run 只持久化一次 run.started 事件。"""
        async with self._uow_factory() as uow:
            existing = await uow.events.list_after(run_id)
            if any(event.event_type is EventType.RUN_STARTED for event in existing):
                return
            event = await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.RUN_STARTED,
                    payload={},
                )
            )
            await uow.commit()
        await self._publish_events([event])

    async def _publish_delta(self, run_id: str, chunk: ModelChunk) -> None:
        """把模型文本与 reasoning 增量作为临时事件发布。"""
        if chunk.text:
            await self._publish_event(
                EventEnvelope(
                    run_id=run_id,
                    event_type=EventType.MESSAGE_DELTA,
                    payload={"text": chunk.text},
                )
            )
        if chunk.reasoning:
            await self._publish_event(
                EventEnvelope(
                    run_id=run_id,
                    event_type=EventType.REASONING_DELTA,
                    payload={"text": chunk.reasoning},
                )
            )

    async def _publish_events(self, events: list[RunEvent]) -> None:
        for event in events:
            await self._publish_event(
                EventEnvelope(
                    event_id=event.id,
                    run_id=event.run_id,
                    event_type=event.event_type,
                    payload=event.payload,
                    created_at=event.created_at,
                )
            )

    async def _publish_event(self, envelope: EventEnvelope) -> None:
        try:
            await self._event_publisher.publish(envelope)
        except Exception:
            # 事件发布失败不能回滚已经提交的执行事实。
            logger.warning(
                "发布 Run 事件失败: run_id=%s event_id=%s",
                envelope.run_id,
                envelope.event_id,
                exc_info=True,
            )

    async def _load_run(self, run_id: str) -> Run:
        async with self._uow_factory() as uow:
            return await uow.runs.get(run_id)
