"""Frame helpers that work the same on a DataFrame or a LazyFrame."""

from collections.abc import Iterable

import polars as pl

__all__ = ["occupied_columns"]


def occupied_columns(frame: pl.DataFrame | pl.LazyFrame, reserved: Iterable[str]) -> set[str]:
    """Every name already taken, so a generated helper column can avoid them.

    Args:
        frame: The frame whose current column names are taken.
        reserved: Further names that are unavailable, such as the schema's
            accepted names, which a later phase may still rename a column to.

    Returns:
        The union of the frame's column names and the reserved names.
    """
    return set(frame.collect_schema().names()) | set(reserved)
