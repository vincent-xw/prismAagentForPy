import pytest
from sqlalchemy.exc import IntegrityError

from prism_agent_kit.db.database import Database

_INSERT_RUN = """
INSERT INTO runs (
    id, session_id, status, input_text, prompt_name, prompt_version,
    system_prompt, model, step_count, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


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
