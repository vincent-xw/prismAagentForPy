from prism_agent_kit.core.digests import canonical_json_digest


def test_canonical_json_digest_is_key_order_independent() -> None:
    left = canonical_json_digest({"b": 2, "a": 1})
    right = canonical_json_digest({"a": 1, "b": 2})

    assert left == right
    assert left.startswith("sha256:")


def test_canonical_json_digest_changes_with_value() -> None:
    assert canonical_json_digest({"a": 1}) != canonical_json_digest({"a": 2})
