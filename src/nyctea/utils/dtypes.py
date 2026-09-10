"""Polars dtype helpers shared across the package."""

import polars as pl

__all__ = ["resolve_dtype"]


def resolve_dtype(dtype: object) -> pl.DataType:
    """Resolve a dtype specification to a Polars DataType.

    Args:
        dtype: A Polars DataType instance or a dtype name string.

    Returns:
        Resolved Polars DataType.

    Raises:
        ValueError: If the dtype is unknown or unsupported.
    """
    if isinstance(dtype, pl.DataType):
        return dtype
    if isinstance(dtype, str):
        candidate = getattr(pl, dtype, None)
        if candidate is None:
            raise ValueError(f"Unknown dtype string '{dtype}'")
        return candidate
    raise ValueError(f"Unsupported dtype specification: {dtype!r}")
