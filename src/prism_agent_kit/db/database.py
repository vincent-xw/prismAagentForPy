from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)


def build_sqlite_url(path: Path) -> str:
    """将文件路径转换为异步 SQLite 连接 URL。"""
    return f"sqlite+aiosqlite:///{path.expanduser().resolve()}"


def _configure_sqlite_connection(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    """为每个新建连接启用本地运行所需的 SQLite 设置。"""
    cursor = dbapi_connection.cursor()
    try:
        # WAL 允许读写并发。busy_timeout 缓解写锁竞争。
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


class Database:
    """持有单个 SQLite 文件的异步引擎与会话工厂。"""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(
            build_sqlite_url(self.path),
            connect_args={"timeout": 30},
        )
        event.listen(self.engine.sync_engine, "connect", _configure_sqlite_connection)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    async def dispose(self) -> None:
        """释放连接池中的全部连接。"""
        await self.engine.dispose()
