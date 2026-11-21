from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from prism_agent_kit.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """提供会正确触发应用生命周期的测试客户端。"""
    with TestClient(app) as test_client:
        yield test_client
