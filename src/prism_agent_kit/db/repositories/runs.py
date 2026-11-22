from datetime import datetime

from sqlalchemy import select, update
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


def _storage_now() -> datetime:
    """返回适合写入 SQLite DateTime 列的当前 UTC 时间。"""
    return utc_now().replace(tzinfo=None)


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
    ) -> Run:
        """先校验状态机再写入目标状态与对应时间戳。"""
        row = await self._session.get(RunRow, run_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.RUN_NOT_FOUND,
                "Run 不存在",
                http_status=404,
                details={"run_id": run_id},
            )

        current = RunStatus(row.status)
        ensure_run_transition(current, target)
        row.status = target.value
        if target is RunStatus.RUNNING and row.started_at is None:
            row.started_at = _storage_now()
        if target in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            row.finished_at = _storage_now()
        if output_text is not None:
            row.output_text = output_text
        if error_code is not None:
            row.error_code = error_code
        if error_message is not None:
            row.error_message = error_message
        if step_count is not None:
            row.step_count = step_count
        await self._session.flush()
        return run_to_domain(row)

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
