"""Built-in parsers, exercised through the registry they are declared into."""

import polars as pl
import pytest

from nyctea import Registry, register_builtins


@pytest.fixture
def parsers():
    registry = Registry()
    register_builtins(registry)
    return registry.column_parsers


def _apply(parsers, name, values):
    frame = pl.DataFrame({"col": values}).lazy()
    return frame.select(parsers.get(name)(pl.col("col")).alias("col")).collect()["col"].to_list()


def test_strip_removes_whitespace(parsers):
    assert _apply(parsers, "strip", ["  hello  ", "  world  "]) == ["hello", "world"]


def test_to_int_casts_and_nulls_failures(parsers):
    assert _apply(parsers, "to_int", ["1", "2", "notanumber"]) == [1, 2, None]


def test_to_float_casts_and_nulls_failures(parsers):
    assert _apply(parsers, "to_float", ["1.5", "oops"]) == [1.5, None]


def test_lower_lowercases(parsers):
    assert _apply(parsers, "lower", ["ABC", "Def"]) == ["abc", "def"]


def test_upper_uppercases(parsers):
    assert _apply(parsers, "upper", ["abc", "Def"]) == ["ABC", "DEF"]


def test_parsers_reject_arguments(parsers):
    """The empty signature after `column` is the contract, so an argument cannot bind."""
    with pytest.raises(ValueError, match="unexpected keyword argument"):
        parsers.get("strip")(pl.col("col"), extra=1)


def test_parsers_chain(parsers):
    frame = pl.DataFrame({"col": ["  ABC  "]}).lazy()
    expr = parsers.get("lower")(parsers.get("strip")(pl.col("col")))
    assert frame.select(expr.alias("col")).collect()["col"].to_list() == ["abc"]
