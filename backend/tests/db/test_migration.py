import os
import sqlite3
import stat
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from prism_agent_kit.core.config import get_settings
from prism_agent_kit.db.database import Database

_INSERT_RUN = """
INSERT INTO runs (
    id, session_id, status, input_text, prompt_name, prompt_version,
    system_prompt, model, step_count, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def test_migrated_database_file_is_private(migrated_database_path: Path) -> None:
    if os.name != "posix":
        return
    assert stat.S_IMODE(migrated_database_path.stat().st_mode) == 0o600


def test_unique_tool_message_migration_rejects_duplicate_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "duplicates.db"
    monkeypatch.setenv("PRISM_AGENT_KIT_DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "20261122_0001")
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("session-1", "demo", "2026-11-22 00:00:00", "2026-11-22 00:00:00"),
            )
            connection.execute(
                _INSERT_RUN,
                (
                    "run-1",
                    "session-1",
                    "succeeded",
                    "input",
                    "default",
                    "1",
                    "system",
                    "test-model",
                    1,
                    "2026-11-22 00:00:00",
                ),
            )
            for value in ("one", "two"):
                connection.execute(
                    """
                    INSERT INTO messages (
                        session_id, run_id, role, content, reasoning,
                        tool_call_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "session-1",
                        "run-1",
                        "tool",
                        f'{{"value": "{value}"}}',
                        None,
                        "call-1",
                        "2026-11-22 00:00:00",
                    ),
                )

        with pytest.raises(RuntimeError, match="重复"):
            command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()


async def test_migration_creates_agent_tables(migrated_database: Database) -> None:
    async with migrated_database.engine.connect() as connection:
        rows = await connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row.name for row in rows}

    assert {"sessions", "runs", "messages", "tool_calls", "run_events"} <= names


async def test_active_run_index_rejects_second_active_run(
    migrated_database: Database,
) -> None:
    async with migrated_database.engine.begin() as connection:
        await connection.exec_driver_sql(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("session-1", "demo", "2026-11-22 00:00:00", "2026-11-22 00:00:00"),
        )
        await connection.exec_driver_sql(
            _INSERT_RUN,
            (
                "run-1",
                "session-1",
                "queued",
                "first",
                "default",
                "1",
                "system",
                "test-model",
                0,
                "2026-11-22 00:00:00",
            ),
        )

        with pytest.raises(IntegrityError):
            await connection.exec_driver_sql(
                _INSERT_RUN,
                (
                    "run-2",
                    "session-1",
                    "running",
                    "second",
                    "default",
                    "1",
                    "system",
                    "test-model",
                    0,
                    "2026-11-22 00:00:01",
                ),
            )


async def test_terminal_run_does_not_block_new_active_run(
    migrated_database: Database,
) -> None:
    async with migrated_database.engine.begin() as connection:
        await connection.exec_driver_sql(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("session-1", "demo", "2026-11-22 00:00:00", "2026-11-22 00:00:00"),
        )
        for run_id, status in (("run-1", "succeeded"), ("run-2", "queued")):
            await connection.exec_driver_sql(
                _INSERT_RUN,
                (
                    run_id,
                    "session-1",
                    status,
                    "input",
                    "default",
                    "1",
                    "system",
                    "test-model",
                    0,
                    "2026-11-22 00:00:00",
                ),
            )
