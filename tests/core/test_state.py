import pytest

from prism_agent_kit.core.enums import RunStatus
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.state import ensure_run_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.QUEUED, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.WAITING_FOR_TOOL),
        (RunStatus.RUNNING, RunStatus.SUCCEEDED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
        (RunStatus.WAITING_FOR_TOOL, RunStatus.QUEUED),
        (RunStatus.WAITING_FOR_TOOL, RunStatus.CANCELLED),
    ],
)
def test_allowed_run_transitions(current: RunStatus, target: RunStatus) -> None:
    ensure_run_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.QUEUED, RunStatus.SUCCEEDED),
        (RunStatus.WAITING_FOR_TOOL, RunStatus.RUNNING),
        (RunStatus.SUCCEEDED, RunStatus.QUEUED),
        (RunStatus.FAILED, RunStatus.RUNNING),
        (RunStatus.CANCELLED, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.RUNNING),
    ],
)
def test_invalid_run_transitions_raise(current: RunStatus, target: RunStatus) -> None:
    with pytest.raises(AgentKitError) as error:
        ensure_run_transition(current, target)

    assert error.value.code is ErrorCode.INVALID_RUN_TRANSITION
    assert error.value.http_status == 409
