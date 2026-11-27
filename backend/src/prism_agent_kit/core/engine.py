import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError
from sqlalchemy.exc import IntegrityError

from prism_agent_kit.application.compaction.summarizer import summarize_span
from prism_agent_kit.application.tool_result_recorder import ToolResultRecorder
from prism_agent_kit.core.compaction import (
    CompactionConfig,
    checkpoint_message,
    prune_tool_results,
    select_compaction_span,
    should_compact,
)
from prism_agent_kit.core.context import ContextAssembler, ContextAssembly
from prism_agent_kit.core.digests import canonical_json_digest
from prism_agent_kit.core.enums import (
    EventType,
    ExecutionMode,
    MessageRole,
    RunStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import (
    CompactionCheckpoint,
    Message,
    Run,
    RunEvent,
    ToolCall,
    utc_now,
)
from prism_agent_kit.core.ports import (
    EventEnvelope,
    EventPublisher,
    ModelChunk,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    WorkspaceLocator,
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


class _CancelRequested(Exception):
    """在持久化模型结果前发现取消请求, 用于回滚本轮写入。"""


class EngineContext(BaseModel):
    """单次引擎执行所需的 Run ID 与协作式取消信号。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    cancel: asyncio.Event


class EngineOutcome(BaseModel):
    """引擎执行结果。不把可恢复失败抛给 Worker。"""

    kind: Literal[
        "completed",
        "waiting_for_tools",
        "waiting_for_approval",
        "failed",
        "cancelled",
    ]
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
        provider_resolver: Callable[[Run], Awaitable[ModelProvider]] | None = None,
        assembler_factory: Callable[[Run], ContextAssembler] | None = None,
        tool_registry: ToolRegistry,
        tool_executor: LocalToolExecutor,
        context_assembler: ContextAssembler,
        event_publisher: EventPublisher,
        max_steps: int,
        max_output_tokens: int | None,
        remote_tool_timeout_seconds: float,
        tool_timeout_seconds: float | None = None,
        tool_result_recorder: ToolResultRecorder | None = None,
        workspace_locator: WorkspaceLocator | None = None,
        approval_timeout_seconds: float = 1800,
        compaction: CompactionConfig | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._model_provider = model_provider
        self._provider_resolver = provider_resolver
        self._assembler_factory = assembler_factory
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._context_assembler = context_assembler
        self._event_publisher = event_publisher
        self._max_steps = max_steps
        self._max_output_tokens = max_output_tokens
        self._remote_tool_timeout_seconds = remote_tool_timeout_seconds
        self._tool_timeout_seconds = tool_timeout_seconds
        self._workspace_locator = workspace_locator
        self._approval_timeout_seconds = approval_timeout_seconds
        self._compaction = compaction or CompactionConfig()
        self._tool_result_recorder = tool_result_recorder or ToolResultRecorder(
            uow_factory=uow_factory,
            event_publisher=event_publisher,
        )

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
        if context.cancel.is_set() or run.cancel_requested_at is not None:
            return await self._cancel_run(run.id)

        provider = (
            await self._provider_resolver(run)
            if self._provider_resolver is not None
            else self._model_provider
        )
        assembler = (
            self._assembler_factory(run)
            if self._assembler_factory is not None
            else self._context_assembler
        )
        max_output_tokens = run.model_max_output_tokens or self._max_output_tokens

        await self._emit_started(run.id)
        workspace_root = None
        permission_mode = None
        if self._workspace_locator is not None:
            workspace_root = await self._workspace_locator.root_for(run.workspace_id)
            if hasattr(self._workspace_locator, "permission_for"):
                permission_mode = await self._workspace_locator.permission_for(run.workspace_id)
        tool_schemas = self._tool_registry.model_schemas()

        while True:
            if await self._is_cancel_requested(run.id, context.cancel):
                return await self._cancel_run(run.id)

            async with self._uow_factory() as uow:
                current = await uow.runs.get(run.id)
                step_count = current.step_count
                messages = await uow.messages.list_for_session(current.session_id)
                history_calls = await uow.tool_calls.list_for_session(current.session_id)
                checkpoint = await uow.checkpoints.latest(current.session_id)

            if step_count >= self._max_steps:
                return await self._fail_run(
                    run.id,
                    ErrorCode.HARNESS_STEP_LIMIT,
                    "Run 已达到最大模型步数",
                )

            messages = self._apply_checkpoint(messages, checkpoint, current.session_id, run.id)
            pruned = prune_tool_results(messages, self._compaction.prune)
            if pruned.pruned_count:
                messages = pruned.messages
                await self._record_event(
                    run.id,
                    EventType.CONTEXT_PRUNED,
                    {
                        "pruned_chars": pruned.pruned_chars,
                        "pruned_count": pruned.pruned_count,
                    },
                )

            if self._compaction.enabled:
                estimated = assembler.estimate_tokens(
                    system_prompt=current.system_prompt,
                    messages=messages,
                    tool_calls=history_calls,
                    tool_schemas=tool_schemas,
                )
                if should_compact(
                    estimated, assembler.input_budget, self._compaction.threshold_ratio
                ):
                    messages = await self._compact_history(
                        run_id=run.id,
                        session_id=current.session_id,
                        system_prompt=current.system_prompt,
                        messages=messages,
                        previous=checkpoint,
                        provider=provider,
                        assembler=assembler,
                        tool_calls=history_calls,
                        tool_schemas=tool_schemas,
                        max_output_tokens=max_output_tokens,
                        force=False,
                    )

            await self._record_event(
                run.id,
                EventType.STEP_STARTED,
                {
                    "step_index": current.step_count,
                    "model": current.model,
                    "model_profile_id": current.model_profile_id,
                },
            )
            step_started_at = time.perf_counter()
            retried_overflow = False
            while True:
                try:
                    assembly = assembler.assemble(
                        system_prompt=current.system_prompt,
                        messages=messages,
                        tool_calls=history_calls,
                        tool_schemas=tool_schemas,
                    )
                except AgentKitError as error:
                    return await self._fail_run(run.id, error.code, error.message)

                try:
                    response = await provider.stream(
                        ModelRequest(
                            system_prompt=current.system_prompt,
                            messages=assembly.messages,
                            tool_calls=history_calls,
                            tools=tool_schemas,
                            max_output_tokens=max_output_tokens,
                        ),
                        on_delta=lambda chunk: self._publish_delta(run.id, chunk),
                    )
                    await self._record_event(
                        run.id,
                        EventType.STEP_COMPLETED,
                        {
                            "step_index": current.step_count,
                            "usage": response.usage.model_dump()
                            if response.usage is not None
                            else None,
                            "duration_ms": round((time.perf_counter() - step_started_at) * 1000, 2),
                            "finish_reason": response.finish_reason,
                            "tool_call_ids": [call.call_id for call in response.tool_calls],
                        },
                    )
                    break
                except asyncio.CancelledError:
                    raise
                except AgentKitError as error:
                    if (
                        error.code is ErrorCode.CONTEXT_OVERFLOW
                        and not retried_overflow
                        and self._compaction.enabled
                    ):
                        retried_overflow = True
                        messages = await self._compact_history(
                            run_id=run.id,
                            session_id=current.session_id,
                            system_prompt=current.system_prompt,
                            messages=messages,
                            previous=checkpoint,
                            provider=provider,
                            assembler=assembler,
                            tool_calls=history_calls,
                            tool_schemas=tool_schemas,
                            max_output_tokens=max_output_tokens,
                            force=True,
                        )
                        continue
                    await self._record_event(
                        run.id,
                        EventType.STEP_FAILED,
                        {
                            "step_index": current.step_count,
                            "error_code": error.code.value,
                            "duration_ms": round((time.perf_counter() - step_started_at) * 1000, 2),
                        },
                    )
                    if await self._is_cancel_requested(run.id, context.cancel):
                        return await self._cancel_run(run.id)
                    return await self._fail_run(run.id, error.code, error.message)

            if await self._is_cancel_requested(run.id, context.cancel):
                return await self._cancel_run(run.id)

            try:
                definitions = self._resolve_tool_definitions(response)
            except AgentKitError as error:
                return await self._fail_run(run.id, error.code, error.message)

            try:
                outcome, calls, ordered_definitions = await self._persist_model_turn(
                    run.id,
                    current.session_id,
                    response,
                    definitions,
                    assembly,
                    context.cancel,
                )
            except _CancelRequested:
                return await self._cancel_run(run.id)
            if outcome is not None:
                return outcome

            if await self._is_cancel_requested(run.id, context.cancel):
                return await self._cancel_run(run.id)

            for call, definition in zip(
                calls,
                ordered_definitions,
                strict=True,
            ):
                try:
                    definition.input_model.model_validate(call.input)
                except ValidationError:
                    return await self._fail_after_contract(
                        run.id,
                        call.id,
                        ToolExecutionResult.failure(
                            ErrorCode.TOOL_INPUT_INVALID,
                            "工具输入不符合 Schema",
                        ),
                    )

            approval_calls: list[ToolCall] = []
            for call, definition in zip(
                calls,
                ordered_definitions,
                strict=True,
            ):
                if definition.execution_mode is ExecutionMode.REMOTE:
                    continue
                if definition.requires_approval:
                    approval_calls.append(call)
                    continue
                if context.cancel.is_set():
                    return await self._cancel_run(run.id)
                async with self._uow_factory() as uow:
                    await uow.tool_calls.start(run.id, call.id)
                    await uow.commit()

                effective_timeout = (
                    min(definition.timeout_seconds, self._tool_timeout_seconds)
                    if self._tool_timeout_seconds is not None
                    else None
                )
                result = await self._tool_executor.execute(
                    definition,
                    call.input,
                    self._make_tool_context(
                        run_id=run.id,
                        session_id=current.session_id,
                        call_id=call.id,
                        cancel=context.cancel,
                        workspace_id=run.workspace_id,
                        workspace_root=workspace_root,
                        permission_mode=permission_mode,
                    ),
                    timeout_seconds=effective_timeout,
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

            if approval_calls:
                if await self._is_cancel_requested(run.id, context.cancel):
                    return await self._cancel_run(run.id)
                return await self._wait_for_approval(run.id, approval_calls)

            if any(
                definition.execution_mode is ExecutionMode.REMOTE
                for definition in ordered_definitions
            ):
                if await self._is_cancel_requested(run.id, context.cancel):
                    return await self._cancel_run(run.id)
                outcome = await self._wait_for_remote_tools(
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
                if await self._is_cancel_requested(run.id, context.cancel):
                    return await self._cancel_run(run.id)
                return outcome

    async def _persist_model_turn(
        self,
        run_id: str,
        session_id: str,
        response: ModelResponse,
        definitions: dict[str, ToolDefinition],
        assembly: ContextAssembly,
        cancel: asyncio.Event,
    ) -> tuple[EngineOutcome | None, list[ToolCall], list[ToolDefinition]]:
        """持久化 assistant 与全部 ToolCall。无工具时直接完成 Run。"""
        persisted_events: list[RunEvent] = []
        try:
            async with self._uow_factory() as uow:
                run = await uow.runs.get(run_id)
                if cancel.is_set() or run.cancel_requested_at is not None:
                    raise _CancelRequested
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
                    if definitions[call.id].requires_approval:
                        payload = self._approval_summary(call)
                    else:
                        payload = {
                            "call_id": call.id,
                            "tool_name": call.tool_name,
                            "execution_mode": call.execution_mode.value,
                            "input": call.input,
                            "input_digest": call.input_digest,
                        }
                    persisted_events.append(
                        await uow.events.append(
                            RunEvent(
                                run_id=run_id,
                                event_type=EventType.TOOL_REQUESTED,
                                payload=payload,
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
                        require_no_cancel_request=True,
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
        except AgentKitError as error:
            if error.code is ErrorCode.RUN_CANCELLED:
                raise _CancelRequested from error
            raise

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
        """把单次本地工具结果委托给共享记录器，保持事件与历史写法一致。"""
        await self._tool_result_recorder.record(run_id, call_id, result)

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

    @staticmethod
    def _approval_summary(call: ToolCall) -> dict[str, JsonValue]:
        """生成需审批调用的安全摘要：文件类保留路径信息，其他工具只给输入预览。"""
        data = call.input if isinstance(call.input, dict) else {}
        if call.tool_name.startswith("file_"):
            content = data.get("content")
            return {
                "call_id": call.id,
                "tool_name": call.tool_name,
                "execution_mode": call.execution_mode.value,
                "kind": "file",
                "path": str(data.get("path", "")),
                "mode": str(data.get("mode", "overwrite")),
                "bytes": len(content.encode("utf-8")) if isinstance(content, str) else 0,
                "input_digest": call.input_digest,
            }
        preview = json.dumps(call.input, ensure_ascii=False)[:4096]
        return {
            "call_id": call.id,
            "tool_name": call.tool_name,
            "execution_mode": call.execution_mode.value,
            "kind": "generic",
            "input_preview": preview,
            "input_digest": call.input_digest,
        }

    def _make_tool_context(
        self,
        *,
        run_id: str,
        session_id: str,
        call_id: str,
        cancel: asyncio.Event,
        workspace_id: str | None,
        workspace_root: Path | None,
        permission_mode: str | None = None,
    ) -> ToolExecutionContext:
        """构造工具上下文，并按需注入工作区根与检索回调。"""
        search = None
        if self._workspace_locator is not None and workspace_id is not None:

            async def search(query: str, limit: int) -> list[object]:
                assert self._workspace_locator is not None
                return await self._workspace_locator.search(workspace_id, query, limit=limit)

        return ToolExecutionContext(
            run_id=run_id,
            session_id=session_id,
            call_id=call_id,
            cancel=cancel,
            workspace_root=workspace_root,
            workspace_id=workspace_id,
            permission_mode=permission_mode,
            search=search,
        )

    async def _wait_for_approval(
        self,
        run_id: str,
        calls: list[ToolCall],
    ) -> EngineOutcome:
        """把需审批的调用置为 awaiting_approval，并让 Run 进入等待审批。"""
        async with self._uow_factory() as uow:
            previous_event_id = await uow.events.last_id(run_id)
            expires_at = utc_now() + timedelta(seconds=self._approval_timeout_seconds)
            for call in calls:
                await uow.tool_calls.await_call(run_id, call.id, expires_at)
            await uow.runs.transition(run_id, RunStatus.WAITING_FOR_APPROVAL)
            await uow.events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=EventType.RUN_WAITING_FOR_APPROVAL,
                    payload={"call_ids": cast(JsonValue, [call.id for call in calls])},
                )
            )
            for call in calls:
                await uow.events.append(
                    RunEvent(
                        run_id=run_id,
                        event_type=EventType.TOOL_APPROVAL_REQUIRED,
                        payload=self._approval_summary(call),
                    )
                )
            new_events = await uow.events.list_after(run_id, after_id=previous_event_id)
            await uow.commit()
        await self._publish_events(new_events)
        return EngineOutcome(kind="waiting_for_approval")

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

    @staticmethod
    def _apply_checkpoint(
        messages: list[Message],
        checkpoint: CompactionCheckpoint | None,
        session_id: str,
        run_id: str,
    ) -> list[Message]:
        """应用最新 checkpoint：只保留 first_kept 之后的消息，摘要置前。"""
        if checkpoint is None:
            return messages
        kept = [
            message
            for message in messages
            if message.id is not None and message.id >= checkpoint.first_kept_message_id
        ]
        return [
            checkpoint_message(session_id=session_id, run_id=run_id, summary=checkpoint.summary),
            *kept,
        ]

    async def _compact_history(
        self,
        *,
        run_id: str,
        session_id: str,
        system_prompt: str,
        messages: list[Message],
        previous: CompactionCheckpoint | None,
        provider: ModelProvider,
        assembler: ContextAssembler,
        tool_calls: list[ToolCall],
        tool_schemas: Sequence[JsonValue],
        max_output_tokens: int | None,
        force: bool,
    ) -> list[Message]:
        """摘要一段旧历史并写 checkpoint；失败只记录事件并继续。"""
        retain = min(
            self._compaction.retain_tokens,
            int(assembler.input_budget * self._compaction.retain_ratio),
        )
        span = select_compaction_span(
            messages,
            retain_tokens=max(retain, 0),
            estimator=assembler.estimator,
        )
        if span is None:
            await self._record_event(
                run_id, EventType.COMPACTION_SKIPPED, {"reason": "nothing_to_compact"}
            )
            return messages
        tokens_before = assembler.estimate_tokens(
            system_prompt=system_prompt,
            messages=messages,
            tool_calls=tool_calls,
            tool_schemas=tool_schemas,
        )
        await self._record_event(
            run_id,
            EventType.COMPACTION_STARTED,
            {"tokens_before": tokens_before, "forced": force},
        )
        try:
            summary = await summarize_span(
                provider,
                span.summarized,
                previous_summary=previous.summary if previous is not None else None,
                max_output_tokens=min(
                    self._compaction.max_summary_output_tokens,
                    max_output_tokens or self._compaction.max_summary_output_tokens,
                ),
                timeout_seconds=self._compaction.timeout_seconds,
            )
        except AgentKitError as error:
            await self._record_event(
                run_id,
                EventType.COMPACTION_FAILED,
                {"error": error.message, "error_code": error.code.value},
            )
            return messages

        kept = [
            message
            for message in messages
            if message.id is not None and message.id >= span.first_kept_message_id
        ]
        rebuilt = [
            checkpoint_message(session_id=session_id, run_id=run_id, summary=summary.text),
            *kept,
        ]
        tokens_after = assembler.estimate_tokens(
            system_prompt=system_prompt,
            messages=rebuilt,
            tool_calls=tool_calls,
            tool_schemas=tool_schemas,
        )
        async with self._uow_factory() as uow:
            checkpoint = await uow.checkpoints.create(
                CompactionCheckpoint(
                    session_id=session_id,
                    summary=summary.text,
                    first_kept_message_id=span.first_kept_message_id,
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                )
            )
            await uow.commit()
        await self._record_event(
            run_id,
            EventType.COMPACTION_COMPLETED,
            {
                "checkpoint_id": checkpoint.id,
                "tokens_before": tokens_before,
                "tokens_after": tokens_after,
                "usage": summary.usage.model_dump() if summary.usage is not None else None,
            },
        )
        return rebuilt

    async def _record_event(
        self, run_id: str, event_type: EventType, payload: dict[str, JsonValue]
    ) -> None:
        """追加并发布一个产品事件。"""
        async with self._uow_factory() as uow:
            event = await uow.events.append(
                RunEvent(run_id=run_id, event_type=event_type, payload=payload)
            )
            await uow.commit()
        await self._publish_events([event])

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

    async def _is_cancel_requested(
        self,
        run_id: str,
        cancel: asyncio.Event,
    ) -> bool:
        """同时检查进程内信号与持久取消标记, 覆盖注册信号前的竞态。"""
        if cancel.is_set():
            return True
        async with self._uow_factory() as uow:
            run = await uow.runs.get(run_id)
        return run.cancel_requested_at is not None

    async def _load_run(self, run_id: str) -> Run:
        async with self._uow_factory() as uow:
            return await uow.runs.get(run_id)
