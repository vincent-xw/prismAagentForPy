from prism_agent_kit.application.mcp.naming import tool_name_for


def test_tool_name_prefix() -> None:
    assert tool_name_for("demo", "search") == "mcp__demo__search"


def test_tool_name_sanitizes_and_truncates() -> None:
    name = tool_name_for("demo", "weird name/with:chars" * 5)
    assert name.startswith("mcp__demo__")
    assert len(name) <= 64
    assert " " not in name and "/" not in name and ":" not in name
