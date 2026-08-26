"""Shared fixtures for engine-level tests."""

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
