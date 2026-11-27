import os

import httpx
import pytest


@pytest.fixture(scope="session")
def base_url() -> str:
    value = os.environ.get("PRISM_CONTRACT_BASE_URL")
    if not value:
        raise RuntimeError("必须设置 PRISM_CONTRACT_BASE_URL")
    return value.rstrip("/")


@pytest.fixture(scope="session")
def token() -> str:
    value = os.environ.get("PRISM_CONTRACT_TOKEN")
    if not value:
        raise RuntimeError("必须设置 PRISM_CONTRACT_TOKEN")
    return value


@pytest.fixture(scope="session")
def client(base_url: str, token: str) -> httpx.Client:
    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as http:
        yield http
