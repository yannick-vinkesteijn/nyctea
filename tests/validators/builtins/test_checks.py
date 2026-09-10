"""Tests for the argument guards on built-in column checks."""

import polars as pl
import pytest

from nyctea.validators.builtins.checks import between, in_set


def test_between_rejects_min_above_max():
    with pytest.raises(ValueError, match="requires min <= max"):
        between(pl.col("x"), min=10, max=1)


def test_in_set_rejects_empty_values():
    with pytest.raises(ValueError, match="non-empty 'values'"):
        in_set(pl.col("x"), values=[])


def test_in_set_builds_is_in_expression():
    result = pl.DataFrame({"x": [1, 2, 3]}).select(in_set(pl.col("x"), values=[1, 2]))
    assert result["x"].to_list() == [True, True, False]
