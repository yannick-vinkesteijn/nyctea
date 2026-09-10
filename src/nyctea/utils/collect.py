"""Collecting a LazyFrame, and choosing the engine to collect it on."""

import polars as pl

from nyctea.types import AggregateEngine

__all__ = ["collect", "pick_aggregate_engine"]


def collect(lf: pl.LazyFrame, engine: AggregateEngine | None = None) -> pl.DataFrame:
    """Collect a LazyFrame, on a specific engine when one is given.

    The engine cannot simply be passed through. Polars' own default is
    ``engine='auto'``, and ``engine=None`` is a ValueError rather than a request for
    that default, so the unset case has to call ``collect()`` with no argument.

    ``engine`` is for pure reductions (sum/len/all/any_horizontal) only. Streaming
    roughly halves peak memory on those (#11) with no correctness difference, since
    none of the reductions used here are approximation-based (unlike e.g.
    ``approx_n_unique``, which does disagree between engines). Row- and cell-level
    materialization needs the default engine, so it leaves ``engine`` unset. The
    value is decided once per ``validate()`` call (see ``schema.streaming_row_threshold``)
    and threaded in via ``context.aggregate_engine`` rather than hardcoded, since
    streaming has a fixed per-query setup cost that makes it slower than the default
    engine on small data.
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
