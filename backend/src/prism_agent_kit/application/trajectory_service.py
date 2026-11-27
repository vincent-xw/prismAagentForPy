"""把事件、消息与工具调用投影成按 Turn/Step 分组的轨迹。"""

from datetime import datetime
from typing import cast

from pydantic import JsonValue

from prism_agent_kit.core.enums import EventType
from prism_agent_kit.core.models import CompactionCheckpoint, Run, RunEvent, ToolCall
from prism_agent_kit.db.uow import UnitOfWorkFactory


class TrajectoryService:
    """只读轨迹投影；新 Run 用 Step 事件，旧 Run 合成 legacy Step。"""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get(
        self, session_id: str, *, limit: int = 50, before: datetime | None = None
    ) -> dict[str, object]:
        async with self._uow_factory() as uow:
            await uow.sessions.get(session_id)
            runs = await uow.runs.list_for_session(session_id, limit=limit, before=before)
            checkpoints = await uow.checkpoints.list_for_session(session_id)
            turns: list[dict[str, object]] = []
            assigned: set[str] = set()
            for run in sorted(runs, key=lambda item: item.created_at):
                events = await uow.events.list_after(run.id)
                tools = await uow.tool_calls.list_for_run(run.id)
                turn = self._turn(run, events, tools, checkpoints)
                turn_compactions = cast(list[dict[str, object]], turn["compactions"])
                assigned.update(str(item["id"]) for item in turn_compactions)
                turns.append(turn)
            orphaned = [item for item in checkpoints if item.id not in assigned]
            if orphaned and turns:
                existing = cast(list[dict[str, object]], turns[-1]["compactions"])
                existing.extend(
                    [
                        {
                            "id": checkpoint.id,
                            "tokens_before": checkpoint.tokens_before,
                            "tokens_after": checkpoint.tokens_after,
                            "created_at": checkpoint.created_at.isoformat(),
                        }
                        for checkpoint in orphaned
                    ]
                )
        return {"turns": turns}

    def _turn(
        self,
        run: Run,
        events: list[RunEvent],
        tools: list[ToolCall],
        checkpoints: list[CompactionCheckpoint],
    ) -> dict[str, object]:
        steps = self._steps(run, events, tools)
        return {
            "run": {
                "id": run.id,
                "status": run.status.value,
                "input_text": run.input_text,
                "created_at": run.created_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "error_code": run.error_code,
                "error_message": run.error_message,
            },
            "steps": steps,
            "compactions": [
                {
                    "id": checkpoint.id,
                    "tokens_before": checkpoint.tokens_before,
                    "tokens_after": checkpoint.tokens_after,
                    "created_at": checkpoint.created_at.isoformat(),
                }
                for checkpoint in checkpoints
                if self._in_run(checkpoint.created_at, run)
            ],
        }

    @staticmethod
    def _in_run(created_at: datetime, run: Run) -> bool:
        if created_at < run.created_at:
            return False
        return run.finished_at is None or created_at <= run.finished_at

    def _steps(
        self, run: Run, events: list[RunEvent], tools: list[ToolCall]
    ) -> list[dict[str, object]]:
        started: dict[int, dict[str, JsonValue]] = {}
        completed: dict[int, dict[str, JsonValue]] = {}
        calls_by_step: dict[int, set[str]] = {}
        legacy = True
        for event in events:
            payload = cast(dict[str, JsonValue], event.payload)
            index = payload.get("step_index")
            if not isinstance(index, int):
                continue
            if event.event_type is EventType.STEP_STARTED:
                legacy = False
                started[index] = payload
            elif event.event_type is EventType.STEP_COMPLETED:
                completed[index] = payload
                ids = payload.get("tool_call_ids")
                if isinstance(ids, list):
                    calls_by_step[index] = {str(call_id) for call_id in ids}
        if legacy:
            return [
                {
                    "index": 0,
                    "model": run.model,
                    "usage": None,
                    "duration_ms": None,
                    "finish_reason": None,
                    "assistant_message_id": None,
                    "tools": [self._tool(tool) for tool in tools],
                    "legacy": True,
                }
            ]
        result: list[dict[str, object]] = []
        for index in sorted(started):
            start = started[index]
            done = completed.get(index, {})
            result.append(
                {
                    "index": index,
                    "model": start.get("model", run.model),
                    "usage": done.get("usage"),
                    "duration_ms": done.get("duration_ms"),
                    "finish_reason": done.get("finish_reason"),
                    "assistant_message_id": None,
                    "tools": [
                        self._tool(tool)
                        for tool in tools
                        if tool.id in calls_by_step.get(index, set())
                    ],
                    "legacy": False,
                }
            )
        return result

    @staticmethod
    def _tool(tool: ToolCall) -> dict[str, object]:
        duration = None
        if tool.finished_at is not None:
            duration = round((tool.finished_at - tool.created_at).total_seconds() * 1000, 2)
        return {
            "call_id": tool.id,
            "tool_name": tool.tool_name,
            "status": tool.status.value,
            "duration_ms": duration,
            "input": tool.input,
            "output": tool.output,
        }
