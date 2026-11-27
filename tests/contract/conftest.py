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
    """UI 反代用例只能被显式跳过（PRISM_CONTRACT_SKIP_UI=1）。

    默认行为是"没配 UI 地址就视为失败"，避免 CI 忘记变量时静默变绿。
    """
    if os.environ.get("PRISM_CONTRACT_UI_BASE_URL"):
        return
    if os.environ.get("PRISM_CONTRACT_SKIP_UI") == "1":
        skip = pytest.mark.skip(reason="PRISM_CONTRACT_SKIP_UI=1，显式跳过 UI 反代用例")
        for item in items:
            if "ui_base_url" in getattr(item, "fixturenames", ()):
                item.add_marker(skip)
        return
    pytest.fail(
        "缺少 PRISM_CONTRACT_UI_BASE_URL：要么提供 UI 地址，要么显式设置 PRISM_CONTRACT_SKIP_UI=1",
        pytrace=False,
    )
