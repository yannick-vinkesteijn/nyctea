"""Shared utilities for the validation engine."""

import polars as pl

from nyctea.schema.model import SchemaModel

__all__ = [
    "SchemaResolutionError",
    "_resolve_dtype",
    "resolve_column_names",
]


class SchemaResolutionError(ValueError):
    """Raised when columns cannot be resolved from schema definitions."""


def resolve_column_names(schema: SchemaModel, df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame | pl.LazyFrame:
    """Rename columns to canonical names using synonym definitions.

    Args:
        schema: Schema defining columns and synonyms.
        df: Input frame.

    Returns:
        Frame with columns renamed to canonical names where applicable.

    Raises:
        SchemaResolutionError: If required columns are missing or ambiguous.
    """
    columns = set(df.collect_schema().names() if isinstance(df, pl.LazyFrame) else df.columns)
    mapping: dict[str, str] = {}
    used: set[str] = set()

    for canonical, col_schema in schema.columns.items():
        candidates = {canonical} | set(col_schema.synonyms)
        found = [c for c in columns if c in candidates]
        if not found:
            if col_schema.required:
                raise SchemaResolutionError(
                    f"Required column '{canonical}' is missing. Looked for: {sorted(candidates)}"
                )
            continue
        if len(found) > 1:
            raise SchemaResolutionError(
                f"Ambiguous columns for '{canonical}': {found}. Only one canonical/synonym is allowed."
            )
        physical = found[0]
        if physical in used:
            raise SchemaResolutionError(f"Column '{physical}' is mapped multiple times.")
        used.add(physical)
        if physical != canonical:
            mapping[physical] = canonical

    if not mapping:
        return df
    return df.rename(mapping)


def _resolve_dtype(dtype: object) -> pl.DataType:
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
