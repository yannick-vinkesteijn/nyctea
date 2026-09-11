"""Schema-aware CSV and Parquet reading.

Default (`typed=False`) reads every column as Utf8, so validation controls type
coercion instead of Polars' own inference.
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
        lazy: Optional override. Defaults to the schema, then `nyctea.Config`.
        typed: When True, read with schema-declared dtypes (like Pandera/Patito).
            When False (default), read all columns as Utf8 and rely on parsing/coercion.

    Returns:
        pl.LazyFrame or pl.DataFrame depending on lazy flag.
    """
    use_lazy = schema.resolved_lazy if lazy is None else lazy

    if typed:
        dtype_overrides = {}
        for canonical_name, col_schema in schema.columns.items():
            target_dtype = _to_dtype(col_schema.dtype)
            dtype_overrides[canonical_name] = target_dtype
            for synonym in col_schema.synonyms:
                dtype_overrides[synonym] = target_dtype

        if use_lazy:
            return pl.scan_csv(path, schema_overrides=dtype_overrides)
        return pl.read_csv(path, schema_overrides=dtype_overrides)
    if use_lazy:
        return pl.scan_csv(path, infer_schema=False)
    return pl.read_csv(path, infer_schema=False)


def read_parquet(
    path: str | Path | list[str] | list[Path],
    schema: SchemaModel,
    lazy: bool | None = None,
) -> pl.DataFrame | pl.LazyFrame:
    """Read Parquet using native types from the file.

    Args:
        path: Path or paths to Parquet files.
        schema: SchemaModel describing the expected columns.
        lazy: Optional override. Defaults to the schema, then `nyctea.Config`.

    Returns:
        pl.LazyFrame or pl.DataFrame depending on lazy flag.
    """
    use_lazy = schema.resolved_lazy if lazy is None else lazy
    if use_lazy:
        return pl.scan_parquet(path)
    return pl.read_parquet(path)


__all__ = ["read_csv", "read_parquet"]
