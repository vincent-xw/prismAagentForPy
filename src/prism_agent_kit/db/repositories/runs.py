from datetime import datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.enums import RunStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Run, utc_now
from prism_agent_kit.core.state import ensure_run_transition
from prism_agent_kit.db.mappers import run_to_domain, run_to_row
from prism_agent_kit.db.models import RunRow, SessionRow

_ACTIVE_STATUSES = (
    RunStatus.QUEUED.value,
    RunStatus.RUNNING.value,
    RunStatus.WAITING_FOR_TOOL.value,
)
_ACTIVE_RUN_STATUSES = frozenset(
    {
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.WAITING_FOR_TOOL,
    }
)


def _storage_now() -> datetime:
    """返回适合写入 SQLite DateTime 列的当前 UTC 时间。"""
    return utc_now().replace(tzinfo=None)


def _reject_committed_cancel_request(row: RunRow, run_id: str) -> None:
    """取消请求已提交时拒绝非取消终态写入。"""
    status = RunStatus(row.status)
    if status is RunStatus.CANCELLED or (
        status in _ACTIVE_RUN_STATUSES and row.cancel_requested_at is not None
    ):
        raise AgentKitError(
            ErrorCode.RUN_CANCELLED,
            "Run 已请求取消",
            http_status=409,
            details={"run_id": run_id, "status": status.value},
        )


class RunRepository:
    """Run 的读写与原子 claim 仓库。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: Run) -> Run:
        """创建 Run。同一 Session 的活动 Run 冲突会转换为 409。"""
        if await self._session.get(SessionRow, run.session_id) is None:
            raise AgentKitError(
                ErrorCode.SESSION_NOT_FOUND,
                "Session 不存在",
                http_status=404,
                details={"session_id": run.session_id},
            )
        self._session.add(run_to_row(run))
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise AgentKitError(
                ErrorCode.RUN_CONFLICT,
                "当前 Session 已有活动 Run",
                http_status=409,
                details={"session_id": run.session_id},
            ) from error
        return run

    async def get(self, run_id: str) -> Run:
        """按 ID 读取 Run。不存在时抛出 404 领域错误。"""
        row = await self._session.get(RunRow, run_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.RUN_NOT_FOUND,
                "Run 不存在",
                http_status=404,
                details={"run_id": run_id},
            )
        return run_to_domain(row)

    async def get_active(self, session_id: str) -> Run | None:
        """返回 Session 当前的非终止 Run。"""
        row = await self._session.scalars(
            select(RunRow)
            .where(
                RunRow.session_id == session_id,
                RunRow.status.in_(_ACTIVE_STATUSES),
            )
            .order_by(RunRow.created_at.desc())
            .limit(1)
        )
        active = row.first()
        return run_to_domain(active) if active is not None else None

    async def list_by_status(self, status: RunStatus) -> list[Run]:
        """按状态返回 Run。供启动恢复与扫描任务使用。"""
        result = await self._session.scalars(
            select(RunRow)
            .where(RunRow.status == status.value)
            .order_by(RunRow.created_at, RunRow.id)
        )
        return [run_to_domain(row) for row in result]

    async def claim_next(self) -> Run | None:
        """以条件更新原子 claim 最早的 queued Run。"""
        candidate = (
            select(RunRow.id)
            .where(RunRow.status == RunStatus.QUEUED.value)
            .order_by(RunRow.created_at, RunRow.id)
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(RunRow)
            .where(
                RunRow.id == candidate,
                RunRow.status == RunStatus.QUEUED.value,
            )
            .values(
                status=RunStatus.RUNNING.value,
                started_at=_storage_now(),
            )
            .returning(RunRow)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)
        row = result.scalars().one_or_none()
        return run_to_domain(row) if row is not None else None

    async def transition(
        self,
        run_id: str,
        target: RunStatus,
        *,
        output_text: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        step_count: int | None = None,
        require_no_cancel_request: bool = False,
    ) -> Run:
        """用状态条件更新实现 CAS, 避免并发写入覆盖已提交状态。"""
        for _ in range(3):
            row = await self._session.get(
                RunRow,
                run_id,
                populate_existing=True,
            )
            if row is None:
                raise AgentKitError(
                    ErrorCode.RUN_NOT_FOUND,
                    "Run 不存在",
                    http_status=404,
                    details={"run_id": run_id},
                )

            current = RunStatus(row.status)
            if require_no_cancel_request:
                _reject_committed_cancel_request(row, run_id)
            ensure_run_transition(current, target)
            values: dict[str, object] = {"status": target.value}
            if target is RunStatus.RUNNING and row.started_at is None:
                values["started_at"] = _storage_now()
            if target in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                values["finished_at"] = _storage_now()
            if output_text is not None:
                values["output_text"] = output_text
            if error_code is not None:
                values["error_code"] = error_code
            if error_message is not None:
                values["error_message"] = error_message
            if step_count is not None:
                values["step_count"] = step_count

            statement = update(RunRow).where(
                RunRow.id == run_id,
                RunRow.status == current.value,
            )
            if require_no_cancel_request:
                statement = statement.where(RunRow.cancel_requested_at.is_(None))
            result = cast(
                CursorResult[Any],
                await self._session.execute(
                    statement.values(values).execution_options(synchronize_session=False)
                ),
            )
            if result.rowcount == 1:
                updated = await self._session.get(
                    RunRow,
                    run_id,
                    populate_existing=True,
                )
                if updated is None:
                    raise AgentKitError(
                        ErrorCode.RUN_NOT_FOUND,
                        "Run 不存在",
                        http_status=404,
                        details={"run_id": run_id},
                    )
                return run_to_domain(updated)

            latest = await self._session.get(
                RunRow,
                run_id,
                populate_existing=True,
            )
            if latest is not None:
                if require_no_cancel_request:
                    _reject_committed_cancel_request(latest, run_id)
                if latest.status == target.value:
                    # 同一目标已由并发路径提交, 按幂等成功返回。
                    return run_to_domain(latest)

        raise AgentKitError(
            ErrorCode.INVALID_RUN_TRANSITION,
            "Run 状态被并发修改, 无法完成迁移",
            http_status=409,
            details={"run_id": run_id, "target": target.value},
        )

    async def update_step_count(self, run_id: str, step_count: int) -> Run:
        """更新已执行的模型请求次数。"""
        row = await self._session.get(RunRow, run_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.RUN_NOT_FOUND,
                "Run 不存在",
                http_status=404,
                details={"run_id": run_id},
            )
        row.step_count = step_count
        await self._session.flush()
        return run_to_domain(row)

    async def mark_cancel_requested(self, run_id: str) -> Run:
        """仅给非终止 Run 记录取消请求时间。重复调用保持幂等。"""
        await self._session.execute(
            update(RunRow)
            .where(
                RunRow.id == run_id,
                RunRow.status.in_(_ACTIVE_STATUSES),
                RunRow.cancel_requested_at.is_(None),
            )
            .values(cancel_requested_at=_storage_now())
            .execution_options(synchronize_session=False)
        )
        row = await self._session.get(
            RunRow,
            run_id,
            populate_existing=True,
        )
        if row is None:
            raise AgentKitError(
                ErrorCode.RUN_NOT_FOUND,
                "Run 不存在",
                http_status=404,
                details={"run_id": run_id},
            )
        return run_to_domain(row)
