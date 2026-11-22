import pytest

from prism_agent_kit.core.token_budget import TiktokenEstimator


def test_tiktoken_estimator_counts_with_explicit_encoding() -> None:
    estimator = TiktokenEstimator("cl100k_base")

    assert estimator.count_text("hello world") > 0
    assert estimator.count_text("hello world") == estimator.count_text("hello world")


def test_unknown_encoding_fails_instead_of_falling_back() -> None:
    with pytest.raises(ValueError):
        TiktokenEstimator("not-a-real-encoding")
