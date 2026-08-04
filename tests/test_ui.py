from __future__ import annotations

import pytest

from paddle_cli.ui import pagination_query, parse_typed_value, shorten


def test_parse_typed_values() -> None:
    assert parse_typed_value("12", {"type": "integer"}) == 12
    assert parse_typed_value("1.5", {"type": "number"}) == 1.5
    assert parse_typed_value("yes", {"type": "boolean"}) is True
    assert parse_typed_value('["a","b"]', {"type": "array"}) == ["a", "b"]
    assert parse_typed_value('{"a":1}', {"type": "object"}) == {"a": 1}


def test_invalid_typed_value_has_actionable_error() -> None:
    with pytest.raises(ValueError, match="whole number"):
        parse_typed_value("abc", {"type": "integer"})


def test_pagination_query_reads_cursor() -> None:
    assert pagination_query("https://api.paddle.com/products?after=pro_123&per_page=20") == {
        "after": "pro_123",
        "per_page": "20",
    }


def test_shorten_normalizes_whitespace() -> None:
    assert shorten("one\n two", 20) == "one two"
    assert shorten("abcdefghijklmnopqrstuvwxyz", 10) == "abcdefghi…"
