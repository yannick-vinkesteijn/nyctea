"""Shared fixtures."""

import polars as pl
import pytest


@pytest.fixture
def collect_calls(monkeypatch):
    """Record each pl.LazyFrame.collect() call's kwargs, in call order.

    Use len(calls) to assert collect count, or calls[i].get("engine") to
    assert which engine a specific call used.
    """
    calls = []
    orig_collect = pl.LazyFrame.collect

    def recording_collect(self, *args, **kwargs):
        calls.append(kwargs)
        return orig_collect(self, *args, **kwargs)

    monkeypatch.setattr(pl.LazyFrame, "collect", recording_collect)
    return calls


@pytest.fixture
def schema_resolutions(monkeypatch):
    """Record each pl.LazyFrame.collect_schema() call, in call order.

    Resolving a lazy plan's schema is not free and the engine caches it, so the
    count is a property worth pinning rather than an implementation detail.
    """
    calls = []
    original = pl.LazyFrame.collect_schema

    def recording(self):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(pl.LazyFrame, "collect_schema", recording)
    return calls
