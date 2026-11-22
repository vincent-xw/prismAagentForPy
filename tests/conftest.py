from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prism_agent_kit.core.config import Settings
from prism_agent_kit.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """提供会正确触发应用生命周期的测试客户端。"""
    application = create_app(Settings(database_path=tmp_path / "agent.db"))
    with TestClient(application) as test_client:
        yield test_client
