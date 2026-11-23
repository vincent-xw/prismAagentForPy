from datetime import UTC, datetime
from enum import StrEnum

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.enums import (
    EventType,
    MessageRole,
    ToolCallStatus,
)
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, RunEvent, ToolCall, utc_now
from prism_agent_kit.db.mappers import tool_call_to_domain, tool_call_to_row
from prism_agent_kit.db.models import MessageRow, RunRow, ToolCallRow
from prism_agent_kit.db.repositories.events import EventRepository
from prism_agent_kit.db.repositories.messages import MessageRepository


class CompleteToolResult(StrEnum):
    """远端工具结果回填的幂等结果。"""

    COMMITTED = "committed"
    ALREADY_COMMITTED = "already_committed"


def _storage_now() -> datetime:
    return utc_now().replace(tzinfo=None)


def _error_content(code: ErrorCode, message: str) -> dict[str, JsonValue]:
    """生成闭合工具调用时写入历史的结构化错误内容。"""
    return {"error": {"code": code.value, "message": message}}


class ToolCallRepository:
    """工具调用的持久化与幂等结果提交。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._messages = MessageRepository(session)
        self._events = EventRepository(session)

    async def create_many(self, tool_calls: list[ToolCall]) -> list[ToolCall]:
        """批量创建工具调用。由调用方提交事务。"""
        rows = [tool_call_to_row(tool_call) for tool_call in tool_calls]
        self._session.add_all(rows)
        await self._session.flush()
        return [tool_call_to_domain(row) for row in rows]

    async def get(self, run_id: str, call_id: str) -> ToolCall:
        """读取指定 Run 下的工具调用。"""
        row = await self._session.get(ToolCallRow, call_id)
        if row is None or row.run_id != run_id:
            raise AgentKitError(
                ErrorCode.TOOL_CALL_NOT_FOUND,
                "ToolCall 不存在",
                http_status=404,
                details={"run_id": run_id, "call_id": call_id},
            )
        return tool_call_to_domain(row)

    async def list_for_run(self, run_id: str) -> list[ToolCall]:
        """按创建顺序返回 Run 的全部工具调用。"""
        result = await self._session.scalars(
            select(ToolCallRow)
            .where(ToolCallRow.run_id == run_id)
            .order_by(ToolCallRow.created_at, ToolCallRow.id)
        )
        return [tool_call_to_domain(row) for row in result]

    async def list_for_session(self, session_id: str) -> list[ToolCall]:
        """返回 Session 全部 Run 下的工具调用。供历史重建。"""
        result = await self._session.scalars(
            select(ToolCallRow)
            .join(RunRow, ToolCallRow.run_id == RunRow.id)
            .where(RunRow.session_id == session_id)
            .order_by(ToolCallRow.created_at, ToolCallRow.id)
        )
        return [tool_call_to_domain(row) for row in result]

    async def list_expired(self, now: datetime) -> list[ToolCall]:
        """返回已超过回填截止时间且仍未完成的工具调用。"""
        storage_now = now.astimezone(UTC).replace(tzinfo=None)
        result = await self._session.scalars(
            select(ToolCallRow)
            .where(
                ToolCallRow.status.in_(
                    (ToolCallStatus.PENDING.value, ToolCallStatus.RUNNING.value)
                ),
                ToolCallRow.expires_at.is_not(None),
                ToolCallRow.expires_at <= storage_now,
            )
            .order_by(ToolCallRow.expires_at, ToolCallRow.id)
        )
        return [tool_call_to_domain(row) for row in result]

    async def start(self, run_id: str, call_id: str) -> ToolCall:
        """把待执行工具调用原子标记为 running。"""
        row = await self._require_call(run_id, call_id)
        if ToolCallStatus(row.status) is not ToolCallStatus.PENDING:
            raise AgentKitError(
                ErrorCode.TOOL_RESULT_CONFLICT,
                "ToolCall 状态不允许开始执行",
                http_status=409,
                details={"call_id": call_id},
            )
        row.status = ToolCallStatus.RUNNING.value
        await self._session.flush()
        return tool_call_to_domain(row)

    async def await_call(
        self,
        run_id: str,
        call_id: str,
        expires_at: datetime,
    ) -> ToolCall:
        """把待执行工具调用标记为等待审批并写入截止时间。"""
        row = await self._require_call(run_id, call_id)
        if ToolCallStatus(row.status) is not ToolCallStatus.PENDING:
            raise AgentKitError(
                ErrorCode.TOOL_RESULT_CONFLICT,
                "ToolCall 状态不允许进入待审批",
                http_status=409,
                details={"call_id": call_id},
            )
        row.status = ToolCallStatus.AWAITING_APPROVAL.value
        row.expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
        await self._session.flush()
        return tool_call_to_domain(row)

    async def fail(
        self,
        run_id: str,
        call_id: str,
        error_code: ErrorCode | str,
        message: str,
    ) -> Message:
        """记录单次工具失败结果。不闭合同轮其他调用。"""
        row = await self._require_call(run_id, call_id)
        if ToolCallStatus(row.status) in {
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.FAILED,
            ToolCallStatus.EXPIRED,
            ToolCallStatus.CANCELLED,
        }:
            raise AgentKitError(
                ErrorCode.TOOL_RESULT_CONFLICT,
                "ToolCall 已进入终态",
                http_status=409,
                details={"call_id": call_id},
            )
        run = await self._require_run(run_id)
        code_value = error_code.value if isinstance(error_code, ErrorCode) else error_code
        if code_value == ErrorCode.REMOTE_TOOL_TIMEOUT.value:
            tool_status = ToolCallStatus.EXPIRED
            event_type = EventType.TOOL_EXPIRED
        elif code_value == ErrorCode.RUN_CANCELLED.value:
            tool_status = ToolCallStatus.CANCELLED
            event_type = EventType.TOOL_FAILED
        else:
            tool_status = ToolCallStatus.FAILED
            event_type = EventType.TOOL_FAILED
        tool_message = await self._messages.append(
            Message(
                session_id=run.session_id,
                run_id=run_id,
                role=MessageRole.TOOL,
                content={
                    "error": {
                        "code": code_value,
                        "message": message,
                    }
                },
                tool_call_id=call_id,
            )
        )
        row.status = tool_status.value
        row.error_code = code_value
        row.error_message = message
        row.finished_at = _storage_now()
        await self._events.append(
            RunEvent(
                run_id=run_id,
                event_type=event_type,
                payload={
                    "call_id": call_id,
                    "tool_name": row.tool_name,
                    "error_code": code_value,
                    "error_message": message,
                    "message_id": tool_message.id,
                },
            )
        )
        await self._session.flush()
        return tool_message

    async def complete(
        self,
        run_id: str,
        call_id: str,
        output: JsonValue,
    ) -> CompleteToolResult:
        """原子提交远端工具结果。重复相同结果幂等。冲突结果不写历史。"""
        row = await self._session.get(ToolCallRow, call_id)
        if row is None or row.run_id != run_id:
            raise AgentKitError(
                ErrorCode.TOOL_CALL_NOT_FOUND,
                "ToolCall 不存在",
                http_status=404,
                details={"run_id": run_id, "call_id": call_id},
            )

        status = ToolCallStatus(row.status)
        existing = await self._find_tool_message(run_id, call_id)
        if status is ToolCallStatus.SUCCEEDED:
            if existing is None:
                raise AgentKitError(
                    ErrorCode.TOOL_RESULT_CONFLICT,
                    "ToolCall 已完成但历史消息缺失",
                    http_status=409,
                    details={"call_id": call_id},
                )
            if existing.content != output:
                raise AgentKitError(
                    ErrorCode.TOOL_RESULT_CONFLICT,
                    "ToolCall 已提交不同结果",
                    http_status=409,
                    details={"call_id": call_id},
                )
            return CompleteToolResult.ALREADY_COMMITTED
        if status is ToolCallStatus.EXPIRED:
            raise AgentKitError(
                ErrorCode.TOOL_CALL_EXPIRED,
                "ToolCall 已过期",
                http_status=409,
                details={"call_id": call_id},
            )
        if status in {
            ToolCallStatus.FAILED,
            ToolCallStatus.CANCELLED,
        }:
            raise AgentKitError(
                ErrorCode.TOOL_RESULT_CONFLICT,
                "ToolCall 已由错误结果闭合",
                http_status=409,
                details={"call_id": call_id},
            )

        run = await self._require_run(run_id)
        message = await self._messages.append(
            Message(
                session_id=run.session_id,
                run_id=run_id,
                role=MessageRole.TOOL,
                content=output,
                tool_call_id=call_id,
            )
        )
        row.status = ToolCallStatus.SUCCEEDED.value
        row.output = output
        row.finished_at = _storage_now()
        await self._events.append(
            RunEvent(
                run_id=run_id,
                event_type=EventType.TOOL_COMPLETED,
                payload={
                    "call_id": call_id,
                    "tool_name": row.tool_name,
                    "message_id": message.id,
                },
            )
        )
        await self._session.flush()
        return CompleteToolResult.COMMITTED

    async def close_open_calls(
        self,
        run_id: str,
        error_code: ErrorCode,
        message: str,
    ) -> list[Message]:
        """为 Run 的所有未完成工具调用补齐错误消息与终态。"""
        run = await self._require_run(run_id)
        result = await self._session.scalars(
            select(ToolCallRow)
            .where(
                ToolCallRow.run_id == run_id,
                ToolCallRow.status.in_(
                    (ToolCallStatus.PENDING.value, ToolCallStatus.RUNNING.value)
                ),
            )
            .order_by(ToolCallRow.created_at, ToolCallRow.id)
        )
        rows = list(result)
        closed_messages: list[Message] = []
        for row in rows:
            tool_status, event_type = self._closure_status(error_code)
            content = _error_content(error_code, message)
            closed_message = await self._messages.append(
                Message(
                    session_id=run.session_id,
                    run_id=run_id,
                    role=MessageRole.TOOL,
                    content=content,
                    tool_call_id=row.id,
                )
            )
            row.status = tool_status.value
            row.error_code = error_code.value
            row.error_message = message
            row.finished_at = _storage_now()
            await self._events.append(
                RunEvent(
                    run_id=run_id,
                    event_type=event_type,
                    payload={
                        "call_id": row.id,
                        "tool_name": row.tool_name,
                        "error_code": error_code.value,
                        "error_message": message,
                        "message_id": closed_message.id,
                    },
                )
            )
            closed_messages.append(closed_message)
        await self._session.flush()
        return closed_messages

    async def _find_tool_message(self, run_id: str, call_id: str) -> MessageRow | None:
        result = await self._session.scalars(
            select(MessageRow)
            .where(
                MessageRow.run_id == run_id,
                MessageRow.tool_call_id == call_id,
                MessageRow.role == MessageRole.TOOL.value,
            )
            .limit(1)
        )
        return result.first()

    async def _require_run(self, run_id: str) -> RunRow:
        run = await self._session.get(RunRow, run_id)
        if run is None:
            raise AgentKitError(
                ErrorCode.RUN_NOT_FOUND,
                "Run 不存在",
                http_status=404,
                details={"run_id": run_id},
            )
        return run

    async def _require_call(self, run_id: str, call_id: str) -> ToolCallRow:
        row = await self._session.get(ToolCallRow, call_id)
        if row is None or row.run_id != run_id:
            raise AgentKitError(
                ErrorCode.TOOL_CALL_NOT_FOUND,
                "ToolCall 不存在",
                http_status=404,
                details={"run_id": run_id, "call_id": call_id},
            )
        return row

    @staticmethod
    def _closure_status(error_code: ErrorCode) -> tuple[ToolCallStatus, EventType]:
        """根据闭合原因决定工具状态与事件类型。"""
        if error_code is ErrorCode.REMOTE_TOOL_TIMEOUT:
            return ToolCallStatus.EXPIRED, EventType.TOOL_EXPIRED
        if error_code is ErrorCode.RUN_CANCELLED:
            return ToolCallStatus.CANCELLED, EventType.TOOL_FAILED
        return ToolCallStatus.FAILED, EventType.TOOL_FAILED
