import pytest

from hermes.context import ContextCompactor, ContextItem


def item(source: str, content: str) -> ContextItem:
    return ContextItem(source=source, project="P", content=content)


def test_compaction_preserves_order_and_reports_truncation_and_omission() -> None:
    items = [
        item("a", "a" * 200),
        item("b", "b" * 900),
        item("c", "c" * 400),
    ]
    result = ContextCompactor().compact(items, max_chars=900)
    assert [entry.source for entry in result.items] == ["a", "b"]
    assert result.items[0].content == "a" * 200
    assert "Hermes tool output truncated" in result.items[1].content
    assert result.truncated_sources == ["b"]
    assert result.omitted_sources == ["c"]
    assert result.retained_chars <= 900
    assert result.original_chars == 1500


def test_pinned_context_is_preserved_integrally_and_in_original_order() -> None:
    items = [
        item("regular", "r" * 700),
        item("policy", "p" * 300),
        item("later", "l" * 300),
    ]
    result = ContextCompactor().compact(
        items,
        max_chars=900,
        pinned_sources={"policy"},
    )
    assert [entry.source for entry in result.items] == ["regular", "policy"]
    policy = next(entry for entry in result.items if entry.source == "policy")
    assert policy.content == "p" * 300
    assert "regular" in result.truncated_sources
    assert "later" in result.omitted_sources


def test_pinned_context_fails_closed_when_it_exceeds_budget() -> None:
    with pytest.raises(ValueError, match="pinned context"):
        ContextCompactor().compact(
            [item("policy", "x" * 600)],
            max_chars=512,
            pinned_sources={"policy"},
        )


def test_duplicate_source_names_do_not_duplicate_compacted_items() -> None:
    items = [
        item("same", "a" * 200),
        item("same", "b" * 200),
        item("third", "c" * 200),
    ]
    result = ContextCompactor().compact(items, max_chars=512)
    assert len(result.items) == 2
    assert result.items[0].content == "a" * 200
    assert result.items[1].content.startswith("b")
