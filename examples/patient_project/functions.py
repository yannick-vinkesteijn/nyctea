"""Patient example registry with simple parsers and checks."""


import polars as pl

from nyctea.functions import FunctionRegistry

registry = FunctionRegistry()


@registry.column_parser(name="strip")
def strip(col: pl.Expr) -> pl.Expr:
    """Trim whitespace from strings."""
    return col.str.strip_chars()


@registry.column_parser(name="to_int")
def to_int(col: pl.Expr) -> pl.Expr:
    """Cast values to Int64."""
    return col.cast(pl.Int64)


@registry.column_check(name="non_null")
def non_null(col: pl.Expr) -> pl.Expr:
    """Ensure values are not null."""
    return col.is_not_null()


@registry.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    """Ensure values are strictly positive."""
    return col.gt(0)

@registry.column_check(name="unique_patient_id")
def unique_patient_id(col: pl.Expr) -> pl.Expr:
    """Ensure patient_id values are unique."""
    return col.is_unique()


@registry.frame_parser(name="strip_strings")
def strip_strings(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Strip whitespace from all Utf8 columns."""
    return lf.with_columns(pl.col(pl.Utf8).str.strip_chars())


__all__ = ["registry"]
