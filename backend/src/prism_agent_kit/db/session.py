from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from prism_agent_kit.db.database import Database


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """为单次请求提供独立数据库会话。"""
    database: Database = request.app.state.database
    async with database.session_factory() as session:
        yield session
