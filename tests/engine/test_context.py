"""Guards on `PipelineContext`'s cached view of the frame."""

import polars as pl
import pytest

from nyctea import Registry, SchemaModel
from nyctea.engine.context import PipelineContext


@pytest.fixture
def context():
    schema = SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64"}}})
    return PipelineContext(data=pl.LazyFrame({"a": [1, 2]}), schema=schema, registry=Registry())


def test_frame_schema_refreshes_when_data_changes(context):
    """A phase replaces `data`, so the cache must follow it without being told."""
    assert context.get_column_names() == ["a"]

    context.data = context.data.with_columns(pl.lit(1).alias("b"))

    assert context.get_column_names() == ["a", "b"]


def test_frame_schema_is_cached_per_frame(monkeypatch, context):
    """Repeated reads of one frame resolve its plan once, not once per caller."""
    calls = []
    original = pl.LazyFrame.collect_schema
    monkeypatch.setattr(
        pl.LazyFrame,
        "collect_schema",
        lambda self: (calls.append(1), original(self))[1],
    )

    context.get_column_names()
    context.get_column_names()
    context.frame_schema()
    assert len(calls) == 1

    context.data = context.data.with_columns(pl.lit(1).alias("b"))
    context.get_column_names()
    assert len(calls) == 2
