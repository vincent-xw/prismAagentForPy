from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from prism_agent_kit.core.config import Settings, get_settings
from prism_agent_kit.db.database import Database
from prism_agent_kit.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """提供会正确触发应用生命周期的测试客户端。"""
    application = create_app(Settings(database_path=tmp_path / "agent.db"))
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def migrated_database_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """在临时目录执行 Alembic 迁移并返回数据库路径。"""
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv("PRISM_AGENT_KIT_DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        get_settings.cache_clear()
    return database_path


@pytest.fixture
async def migrated_database(migrated_database_path: Path) -> AsyncIterator[Database]:
    """提供已完成迁移的临时数据库实例。"""
    database = Database(migrated_database_path)
    try:
        yield database
    finally:
        await database.dispose()
