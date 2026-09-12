"""The collect wrapper and the engine choice that feeds it."""

import polars as pl
import pytest

from nyctea import Config, SchemaModel
from nyctea.utils.collect import collect, pick_aggregate_engine


def test_collect_uses_given_engine(collect_calls):
    collect(pl.LazyFrame({"a": [1, 2, 3]}).select(pl.col("a").sum()), "streaming")
    assert collect_calls[0].get("engine") == "streaming"


def test_collect_uses_default_engine(collect_calls):
    collect(pl.LazyFrame({"a": [1, 2, 3]}))
    assert collect_calls[0].get("engine") is None


def test_pick_engine_df_below_threshold():
    df = pl.DataFrame({"a": range(100)})
    assert pick_aggregate_engine(df, threshold=1000) == "in-memory"


def test_pick_engine_df_above_threshold():
    df = pl.DataFrame({"a": range(1000)})
    assert pick_aggregate_engine(df, threshold=1000) == "streaming"


def test_pick_engine_lazyframe_streams():
    lf = pl.LazyFrame({"a": [1, 2, 3]})
    assert pick_aggregate_engine(lf, threshold=1_000_000) == "streaming"


def test_threshold_rejects_negative():
    """A negative row count is meaningless and would silently invert engine choice."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        Config.set_streaming_row_threshold(-1)


def test_threshold_allows_zero():
    """0 is the deliberate boundary: stream everything, including empty frames."""
    with Config(streaming_row_threshold=0):
        assert SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64"}}}).resolved_streaming_row_threshold == 0
