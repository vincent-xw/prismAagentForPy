import asyncio
import logging
from datetime import datetime
from typing import cast

from pydantic import JsonValue

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.core.engine import AgentEngine, EngineContext, EngineOutcome
from prism_agent_kit.core.enums import (
    EventType,
    RunStatus,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import RunEvent, utc_now
from prism_agent_kit.core.ports import EventEnvelope, EventPublisher
from prism_agent_kit.db.uow import UnitOfWorkFactory

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }
)
_TERMINAL_TOOL_STATUSES = frozenset(
    {
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
        ToolCallStatus.EXPIRED,
        ToolCallStatus.CANCELLED,
    }
)


class RunWorker:
    """从 SQLite claim Run 并在单进程内调度执行的基础设施。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        engine: AgentEngine,
        event_publisher: EventPublisher,
        cancellation_registry: RunCancellationRegistry,
        concurrency: int = 2,
        poll_interval_seconds: float = 0.1,
        sweep_interval_seconds: float = 15.0,
    ) -> None:
        self._uow_factory = uow_factory
        self._engine = engine
        self._event_publisher = event_publisher
        self._cancellation_registry = cancellation_registry
        self._concurrency = concurrency
        self._poll_interval_seconds = poll_interval_seconds
        self._sweep_interval_seconds = sweep_interval_seconds
        self._stop_event: asyncio.Event | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False

    async def start(self) -> None:
        """执行启动恢复并开始 claim、执行与过期扫描循环。"""
        if self._started:
            return
        await self.recover_interrupted_runs()
        await self.sweep_expired_tool_calls()
        self._stop_event = asyncio.Event()
        self._started = True
        self._tasks = [
            asyncio.create_task(
                self._worker_loop(),
                name=f"prism-agent-worker-{index}",
            )
            for index in range(self._concurrency)
        ]
        self._tasks.append(
            asyncio.create_task(
                self._sweep_loop(),
                name="prism-agent-expiry-sweeper",
            )
        )

    async def stop(self) -> None:
        """停止全部调度循环与正在执行的引擎任务。"""
        if not self._started or self._stop_event is None:
            return
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._cancellation_registry.clear()
        self._started = False

    async def run_once(self) -> EngineOutcome | None:
        """claim 一个 queued Run 并等待其执行到暂停或终止。"""
        async with self._uow_factory() as uow:
            run = await uow.runs.claim_next()
            await uow.commit()
        if run is None:
            return None

        cancel = self._cancellation_registry.register(run.id)
        try:
            context = EngineContext(run_id=run.id, cancel=cancel)
            if run.step_count == 0:
                outcome = await self._engine.execute(context)
            else:
                outcome = await self._engine.resume(context)
            cancel_outcome = await self._cancel_if_requested(run.id, cancel)
            return cancel_outcome or outcome
        except asyncio.CancelledError:
            raise
        except AgentKitError as error:
            await self._fail_run(run.id, error.code, error.message)
            return EngineOutcome(
                kind="failed",
                error_code=error.code,
                message=error.message,
            )
        except Exception:
            logger.exception("Run 执行出现未分类异常: run_id=%s", run.id)
            await self._fail_run(
                run.id,
                ErrorCode.INTERNAL_ERROR,
                "Run 执行出现未分类异常",
            )
            return EngineOutcome(
                kind="failed",
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Run 执行出现未分类异常",
            )
        finally:
            self._cancellation_registry.unregister(run.id)

    async def _cancel_if_requested(
        self,
        run_id: str,
        cancel: asyncio.Event,
    ) -> EngineOutcome | None:
        """引擎返回后再次确认取消请求, 关闭暂停与完成之间的竞态。"""
        async with self._uow_factory() as uow:
            run = await uow.runs.get(run_id)
        if run.status in _TERMINAL_RUN_STATUSES:
            return None
        if not cancel.is_set() and run.cancel_requested_at is None:
            return None
        return await self._engine.cancel(run_id)

    async def recover_interrupted_runs(self) -> int:
        """把启动时遗留的 running Run 标记为进程中断并闭合工具调用。"""
        async with self._uow_factory() as uow:
            runs = await uow.runs.list_by_status(RunStatus.RUNNING)

        recovered = 0
        for run in runs:
            async with self._uow_factory() as uow:
                current = await uow.runs.get(run.id)
                if current.status is not RunStatus.RUNNING:
                    continue
                previous_event_id = await uow.events.last_id(run.id)
                await uow.tool_calls.close_open_calls(
                    run.id,
                    ErrorCode.PROCESS_INTERRUPTED,
                    "进程中断。Run 未能继续执行",
                )
                await uow.runs.transition(
                    run.id,
                    RunStatus.FAILED,
                    error_code=ErrorCode.PROCESS_INTERRUPTED.value,
                    error_message="进程中断。Run 未能继续执行",
                )
                await uow.events.append(
                    RunEvent(
                        run_id=run.id,
                        event_type=EventType.RUN_FAILED,
                        payload={
                            "error_code": ErrorCode.PROCESS_INTERRUPTED.value,
                            "error_message": "进程中断。Run 未能继续执行",
                        },
                    )
                )
                new_events = await uow.events.list_after(
                    run.id,
                    after_id=previous_event_id,
                )
                await uow.commit()
            await self._publish_events(new_events)
            recovered += 1
        return recovered

    async def sweep_expired_tool_calls(
        self,
        now: datetime | None = None,
    ) -> int:
        """把超时远端工具置为 expired。整轮闭合后重新排队 Run。"""
        effective_now = now or utc_now()
        async with self._uow_factory() as uow:
            expired_calls = await uow.tool_calls.list_expired(effective_now)

        grouped: dict[str, list[str]] = {}
        for call in expired_calls:
            grouped.setdefault(call.run_id, []).append(call.id)

        expired_count = 0
        for run_id, call_ids in grouped.items():
            async with self._uow_factory() as uow:
                run = await uow.runs.get(run_id)
                if run.status not in {
                    RunStatus.WAITING_FOR_TOOL,
                    RunStatus.WAITING_FOR_APPROVAL,
                }:
                    continue
                previous_event_id = await uow.events.last_id(run_id)
                run_expired = 0
                for call_id in call_ids:
                    call = await uow.tool_calls.get(run_id, call_id)
                    if call.status not in {
                        ToolCallStatus.PENDING,
                        ToolCallStatus.RUNNING,
                        ToolCallStatus.AWAITING_APPROVAL,
                    }:
                        continue
                    if call.expires_at is None or call.expires_at > effective_now:
                        continue
                    if call.status is ToolCallStatus.AWAITING_APPROVAL:
                        await uow.tool_calls.fail(
                            run_id,
                            call_id,
                            ErrorCode.TOOL_APPROVAL_TIMEOUT,
                            "写入审批超时",
                        )
                    else:
                        await uow.tool_calls.fail(
                            run_id,
                            call_id,
                            ErrorCode.REMOTE_TOOL_TIMEOUT,
                            "远端工具等待超时",
                        )
                    run_expired += 1

                if run_expired == 0:
                    continue

                calls = await uow.tool_calls.list_for_run(run_id)
                if all(call.status in _TERMINAL_TOOL_STATUSES for call in calls):
                    await uow.runs.transition(run_id, RunStatus.QUEUED)
                    await uow.events.append(
                        RunEvent(
                            run_id=run_id,
                            event_type=EventType.RUN_REQUEUED,
                            payload={
                                "call_ids": cast(
                                    JsonValue,
                                    [call.id for call in calls],
                                ),
                                "reason": ErrorCode.TOOL_APPROVAL_TIMEOUT.value
                                if run.status is RunStatus.WAITING_FOR_APPROVAL
                                else ErrorCode.REMOTE_TOOL_TIMEOUT.value,
                            },
                        )
                    )

                new_events = await uow.events.list_after(
                    run_id,
                    after_id=previous_event_id,
                )
                await uow.commit()
            await self._publish_events(new_events)
            expired_count += run_expired
        return expired_count

    async def _fail_run(
        self,
        run_id: str,
        error_code: ErrorCode,
        message: str,
    ) -> None:
        """Worker 兜底失败路径。在单个事务中闭合工具并写终态。"""
        async with self._uow_factory() as uow:
            run = await uow.runs.get(run_id)
            if run.status in _TERMINAL_RUN_STATUSES:
                return
            previous_event_id = await uow.events.last_id(run_id)
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

    async def _worker_loop(self) -> None:
        """持续 claim 可执行 Run。空队列时等待下一次轮询。"""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                outcome = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker claim 或执行失败")
                outcome = None
            if outcome is None:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval_seconds,
                    )
                except TimeoutError:
                    continue

    async def _sweep_loop(self) -> None:
        """周期性扫描过期远端工具调用。"""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self.sweep_expired_tool_calls()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("远端工具过期扫描失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._sweep_interval_seconds,
                )
            except TimeoutError:
                continue

    async def _publish_events(self, events: list[RunEvent]) -> None:
        for event in events:
            try:
                await self._event_publisher.publish(
                    EventEnvelope(
                        event_id=event.id,
                        run_id=event.run_id,
                        event_type=event.event_type,
                        payload=event.payload,
                        created_at=event.created_at,
                    )
                )
            except Exception:
                logger.warning(
                    "Worker 发布事件失败: run_id=%s event_id=%s",
                    event.run_id,
                    event.id,
                    exc_info=True,
                )
