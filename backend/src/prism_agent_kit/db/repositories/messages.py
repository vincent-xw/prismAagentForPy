from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.models import Message
from prism_agent_kit.db.mappers import message_to_domain, message_to_row
from prism_agent_kit.db.models import MessageRow


class MessageRepository:
    """模型可见消息的持久化仓库。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, message: Message) -> Message:
        """追加一条消息并回填自增 ID。"""
        row = message_to_row(message)
        self._session.add(row)
        await self._session.flush()
        return message_to_domain(row)

    async def list_for_session(self, session_id: str) -> list[Message]:
        """按全局递增 ID 返回 Session 的全部消息。"""
        result = await self._session.scalars(
            select(MessageRow).where(MessageRow.session_id == session_id).order_by(MessageRow.id)
        )
        return [message_to_domain(row) for row in result]
