from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from prism_agent_kit.core.config import get_settings

_engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=_engine,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """为单次请求提供独立数据库会话。"""
    async with async_session_factory() as session:
        yield session


async def dispose_database() -> None:
    """在应用退出时释放数据库连接池。"""
    await _engine.dispose()
