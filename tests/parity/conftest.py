"""两端行为 parity 的 HTTP 客户端；不 import 任何后端代码。"""

import os
from collections.abc import Iterator

import httpx
import pytest


def _url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"必须设置 {name}")
    return value.rstrip("/")


@pytest.fixture(scope="session")
def token() -> str:
    value = os.environ.get("PRISM_PARITY_TOKEN")
    if not value:
        raise RuntimeError("必须设置 PRISM_PARITY_TOKEN")
    return value


@pytest.fixture(scope="session")
def python_client(token: str) -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=_url("PRISM_PARITY_PYTHON_URL"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def java_client(token: str) -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=_url("PRISM_PARITY_JAVA_URL"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    ) as client:
        yield client
