import pytest

from hermes.context_controls import ToolOutputLimiter, ToolSearchIndex
from hermes.domain import ToolSpec


def test_tool_search_loads_only_relevant_tool_metadata() -> None:
    tools = [
        ToolSpec(
            tool_id="github_search",
            owner="research",
            description="search repository code and issues",
            tags={"github", "code", "search"},
        ),
        ToolSpec(
            tool_id="market_quote",
            owner="finance",
            description="retrieve market price",
            tags={"market", "price"},
        ),
    ]
    matches = ToolSearchIndex().search(tools, "github code")
    assert [item.tool_id for item in matches] == ["github_search"]
    assert matches[0].score > 0


def test_tool_search_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        ToolSearchIndex().search([], "x", limit=0)


def test_tool_output_limiter_preserves_head_tail_and_reports_omission() -> None:
    content = "A" * 1000 + "B" * 1000
    result = ToolOutputLimiter(max_chars=512, tail_chars=64).limit(content)
    assert result.truncated
    assert result.original_chars == 2000
    assert result.content.startswith("A")
    assert result.content.endswith("B" * 64)
    assert "Hermes tool output truncated" in result.content
    assert result.omitted_chars > 0


def test_tool_output_limiter_does_not_modify_small_results() -> None:
    result = ToolOutputLimiter(max_chars=512).limit("small")
    assert result.content == "small"
    assert result.truncated is False
    assert result.omitted_chars == 0
