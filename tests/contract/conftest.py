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
def ui_base_url() -> str:
    value = os.environ.get("PRISM_CONTRACT_UI_BASE_URL")
    if not value:
        raise RuntimeError("必须设置 PRISM_CONTRACT_UI_BASE_URL")
    return value.rstrip("/")


@pytest.fixture(scope="session")
def client(base_url: str, token: str) -> httpx.Client:
    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as http:
        yield http


def pytest_collection_modifyitems(config, items):
    """未设置 UI 地址时跳过 UI 反代用例：后端契约与 UI 契约各自独立成链。"""
    if os.environ.get("PRISM_CONTRACT_UI_BASE_URL"):
        return
    skip = pytest.mark.skip(reason="未设置 PRISM_CONTRACT_UI_BASE_URL，跳过 UI 反代用例")
    for item in items:
        if "ui_base_url" in getattr(item, "fixturenames", ()):
            item.add_marker(skip)
