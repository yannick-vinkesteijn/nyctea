"""Collecting a LazyFrame, and choosing the engine to collect it on."""

import polars as pl

from nyctea.types import AggregateEngine

__all__ = ["collect", "pick_aggregate_engine"]


def collect(lf: pl.LazyFrame, engine: AggregateEngine | None = None) -> pl.DataFrame:
    """Collect a LazyFrame, on a specific engine when one is given.

    ``engine=None`` can't be passed through: Polars raises on it instead of treating
    it as "use the default", so the unset case calls ``collect()`` with no argument.
    """
    return lf.collect() if engine is None else lf.collect(engine=engine)


def pick_aggregate_engine(df: pl.DataFrame | pl.LazyFrame, threshold: int) -> AggregateEngine:
    """Decide the engine for this validate() call's internal aggregate collects.

    A LazyFrame input's size is unknown without collecting, and choosing lazy is
    itself a signal of larger/out-of-core intent, so it always gets streaming. An
    eager DataFrame's row count is free (``.height``), so it only pays streaming's
    setup cost once the data is actually large enough to benefit.
    """
    if isinstance(df, pl.DataFrame) and df.height < threshold:
        return "in-memory"
    return "streaming"
