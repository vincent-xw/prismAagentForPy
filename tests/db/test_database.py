import os
import stat
from pathlib import Path

from prism_agent_kit.db.database import Database


async def test_database_enables_sqlite_pragmas(tmp_path: Path) -> None:
    database = Database(tmp_path / "agent.db")

    async with database.engine.connect() as connection:
        journal_mode = await connection.exec_driver_sql("PRAGMA journal_mode")
        foreign_keys = await connection.exec_driver_sql("PRAGMA foreign_keys")

    assert journal_mode.scalar() == "wal"
    assert foreign_keys.scalar() == 1
    await database.dispose()


async def test_database_secures_posix_permissions(tmp_path: Path) -> None:
    if os.name != "posix":
        return
    database_path = tmp_path / "private" / "agent.db"
    database = Database(database_path)
    try:
        assert stat.S_IMODE(database_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(database_path.stat().st_mode) == 0o600
    finally:
        await database.dispose()
