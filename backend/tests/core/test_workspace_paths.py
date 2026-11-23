from pathlib import Path

import pytest

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.workspace_paths import EXCLUDED_DIR_NAMES, resolve_in_workspace


def test_rejects_traversal_and_absolute(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()

    with pytest.raises(AgentKitError) as error:
        resolve_in_workspace(root, "../outside.txt")
    assert error.value.code is ErrorCode.WORKSPACE_PATH_OUTSIDE

    with pytest.raises(AgentKitError) as error:
        resolve_in_workspace(root, "/etc/passwd")
    assert error.value.code is ErrorCode.WORKSPACE_PATH_OUTSIDE


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "secret"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(AgentKitError) as error:
        resolve_in_workspace(root, "link/secret.txt")
    assert error.value.code is ErrorCode.WORKSPACE_PATH_OUTSIDE


def test_allows_nested_and_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "docs").mkdir(parents=True)

    assert resolve_in_workspace(root, "docs/a.md") == (root / "docs" / "a.md").resolve()
    assert resolve_in_workspace(root, "") == root.resolve()


def test_rejects_nul(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()

    with pytest.raises(AgentKitError) as error:
        resolve_in_workspace(root, "a\x00b")
    assert error.value.code is ErrorCode.WORKSPACE_PATH_INVALID


def test_excluded_dir_names() -> None:
    assert {".git", "node_modules"} <= EXCLUDED_DIR_NAMES
