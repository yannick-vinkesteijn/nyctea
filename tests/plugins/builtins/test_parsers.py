"""Tests for built-in parsers."""

import polars as pl
import pytest

from nyctea.plugins.builtins.parsers import (
    LowerParser,
    StripParser,
    ToFloatParser,
    ToIntParser,
    UpperParser,
)


def test_strip_parser():
    """Test StripParser removes whitespace."""
    parser = StripParser()
    assert parser.name == "strip"

    df = pl.DataFrame({"col": ["  hello  ", "  world  "]}).lazy()
    result = df.select(parser(pl.col("col"))).collect()

    assert result["col"].to_list() == ["hello", "world"]


def test_to_int_parser():
    """Test ToIntParser converts to integer."""
    parser = ToIntParser()
    assert parser.name == "to_int"

    df = pl.DataFrame({"col": ["42", "123"]}).lazy()
    result = df.select(parser(pl.col("col"))).collect()

    assert result["col"].to_list() == [42, 123]
    assert result["col"].dtype == pl.Int64


def test_to_float_parser():
    """Test ToFloatParser converts to float."""
    parser = ToFloatParser()
    assert parser.name == "to_float"

    df = pl.DataFrame({"col": ["3.14", "2.71"]}).lazy()
    result = df.select(parser(pl.col("col"))).collect()

    assert result["col"].to_list() == [3.14, 2.71]
    assert result["col"].dtype == pl.Float64


def test_lower_parser():
    """Test LowerParser converts to lowercase."""
    parser = LowerParser()
    assert parser.name == "lower"

    df = pl.DataFrame({"col": ["HELLO", "WORLD"]}).lazy()
    result = df.select(parser(pl.col("col"))).collect()

    assert result["col"].to_list() == ["hello", "world"]


def test_upper_parser():
    """Test UpperParser converts to uppercase."""
    parser = UpperParser()
    assert parser.name == "upper"

    df = pl.DataFrame({"col": ["hello", "world"]}).lazy()
    result = df.select(parser(pl.col("col"))).collect()

    assert result["col"].to_list() == ["HELLO", "WORLD"]


def test_parsers_reject_arguments():
    """Test that parsers reject unexpected arguments."""
    parser = StripParser()

    with pytest.raises(ValueError, match="does not accept arguments"):
        parser.validate_args(unexpected="value")


def test_parsers_chain():
    """Test that parsers can be chained."""
    strip = StripParser()
    lower = LowerParser()

    df = pl.DataFrame({"col": ["  HELLO  ", "  WORLD  "]}).lazy()

    # Chain: strip then lower
    result = df.select(
        lower(strip(pl.col("col")))
    ).collect()

    assert result["col"].to_list() == ["hello", "world"]
