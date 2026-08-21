"""Data ingestion helpers for CSV and Parquet.

This module provides schema-aware data reading functions for CSV and Parquet files.
The readers ensure that all columns are read as strings (Utf8) by default to prevent
premature type inference, allowing the validation engine to handle type coercion with
proper error handling.

Key Features:
    - **Synonym support**: Matches physical column names using canonical names and synonyms
    - **Type control**: Read as strings (default) or with declared dtypes (typed mode)
    - **Lazy/eager modes**: Support both DataFrame and LazyFrame workflows
    - **Polars compatibility**: Uses modern `schema_overrides` parameter

Example:
    Basic CSV reading::

        from nyctea.ingest import read_csv
        from nyctea.schema.model import SchemaModel

        schema = SchemaModel.from_yaml_file("schema.yaml")

        # Read as strings (default) - recommended for validation
        lf = read_csv("data.csv", schema, lazy=True)

        # Read with declared dtypes - like Pandera/Patito
        lf = read_csv("data.csv", schema, lazy=True, typed=True)

    Synonym handling::

        # Schema has canonical name 'passenger_id' with synonym 'PassengerId'
        # CSV file has column 'PassengerId'
        # read_csv will match them automatically
        lf = read_csv("titanic.csv", schema, lazy=True)

Note:
    When `typed=False` (default), all columns are read as Utf8 strings.
    This prevents Polars from inferring types, giving validation full control
    over type coercion and error handling.
"""

from pathlib import Path

import polars as pl

from nyctea.schema.model import SchemaModel

UTF8 = pl.Utf8


def _to_dtype(spec: object) -> pl.DataType:
    if isinstance(spec, pl.DataType):
        return spec
    if isinstance(spec, str):
        dtype = getattr(pl, spec, None)
        if dtype is None:
            raise ValueError(f"Unknown dtype string '{spec}'")
        return dtype
    raise ValueError(f"Unsupported dtype specification: {spec!r}")


def read_csv(
    path: str | Path,
    schema: SchemaModel,
    lazy: bool | None = None,
    *,
    typed: bool = False,
) -> pl.DataFrame | pl.LazyFrame:
    """Read a CSV with all columns as Utf8 without dtype inference.

    Args:
        path: Path to CSV file.
        schema: SchemaModel describing the expected columns.
        lazy: Optional override. Defaults to schema.lazy.
        typed: When True, read with schema-declared dtypes (like Pandera/Patito).
            When False (default), read all columns as Utf8 and rely on parsing/coercion.

    Returns:
        pl.LazyFrame or pl.DataFrame depending on lazy flag.

    Note:
        When typed=False, uses infer_schema=False to read all columns as strings,
        which is more efficient than building a full schema_overrides dict.
        When typed=True, uses schema_overrides with synonym support.
    """
    use_lazy = schema.lazy if lazy is None else lazy

    if typed:
        # Build dtype dict using all possible column names (canonical + synonyms)
        # This ensures we match the actual CSV column names
        dtype_overrides = {}
        for canonical_name, col_schema in schema.columns.items():
            target_dtype = _to_dtype(col_schema.dtype)
            # Add canonical name
            dtype_overrides[canonical_name] = target_dtype
            # Add all synonyms
            for synonym in col_schema.synonyms:
                dtype_overrides[synonym] = target_dtype

        if use_lazy:
            return pl.scan_csv(path, schema_overrides=dtype_overrides)
        return pl.read_csv(path, schema_overrides=dtype_overrides)
    # Simpler approach: disable schema inference to read everything as strings
    if use_lazy:
        return pl.scan_csv(path, infer_schema=False)
    return pl.read_csv(path, infer_schema=False)


def read_parquet(
    path: str | Path | list[str | Path],
    schema: SchemaModel,
    lazy: bool | None = None,
) -> pl.DataFrame | pl.LazyFrame:
    """Read Parquet using native types from the file.

    Args:
        path: Path or paths to Parquet files.
        schema: SchemaModel describing the expected columns.
        lazy: Optional override. Defaults to schema.lazy.

    Returns:
        pl.LazyFrame or pl.DataFrame depending on lazy flag.
    """
    use_lazy = schema.lazy if lazy is None else lazy
    if use_lazy:
        return pl.scan_parquet(path)  # type: ignore[arg-type]
    return pl.read_parquet(path)  # type: ignore[arg-type]


__all__ = ["read_csv", "read_parquet"]
