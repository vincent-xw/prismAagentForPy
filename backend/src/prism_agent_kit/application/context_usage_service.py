"""会话上下文使用量估算（只读，供 UI 展示与压缩提醒）。"""

from typing import Any

from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.enums import RunStatus
from prism_agent_kit.core.token_budget import TiktokenEstimator
from prism_agent_kit.db.uow import UnitOfWorkFactory


class ContextUsageService:
    """按 checkpoint + 增量消息估算当前上下文占用。"""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        settings: Settings,
        estimator: TiktokenEstimator,
    ) -> None:
        self._uow_factory = uow_factory
        self._settings = settings
        self._estimator = estimator

    async def get(self, session_id: str) -> dict[str, Any]:
        async with self._uow_factory() as uow:
            await uow.sessions.get(session_id)
            messages = await uow.messages.list_for_session(session_id)
            runs = await uow.runs.list_for_session(session_id, limit=1)
            checkpoint = await uow.checkpoints.latest(session_id)
            active_runs = False
            for status in (
                RunStatus.QUEUED,
                RunStatus.RUNNING,
                RunStatus.WAITING_FOR_TOOL,
                RunStatus.WAITING_FOR_APPROVAL,
            ):
                if await uow.runs.list_by_status(status):
                    active_runs = True
                    break

        run = runs[0] if runs else None
        window = (
            (run.model_context_window if run and run.model_context_window else None)
            or self._settings.model_context_window
            or 65_536
        )
        max_output = (
            (run.model_max_output_tokens if run and run.model_max_output_tokens else None)
            or self._settings.model_max_output_tokens
            or 8_192
        )
        budget = max(1024, int(window) - int(max_output) - 2048)

        if checkpoint is not None:
            recent = [m for m in messages if m.created_at and m.created_at > checkpoint.created_at]
            used = checkpoint.tokens_after + sum(self._estimator.count_message(m) for m in recent)
        else:
            used = sum(self._estimator.count_message(m) for m in messages)

        percent = round(min(used / budget * 100.0, 999.9), 1) if budget else 0.0
        threshold = 0.85
        last_compaction = None
        if checkpoint is not None:
            last_compaction = {
                "tokens_before": checkpoint.tokens_before,
                "tokens_after": checkpoint.tokens_after,
                "at": checkpoint.created_at.isoformat(),
            }
        return {
            "context_window": int(window),
            "max_output_tokens": int(max_output),
            "budget_tokens": budget,
            "used_tokens": int(used),
            "percent": percent,
            "threshold": threshold,
            "needs_compaction": used >= budget * threshold,
            "compactable": bool(messages) and not active_runs,
            "last_compaction": last_compaction,
        }
