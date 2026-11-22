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
