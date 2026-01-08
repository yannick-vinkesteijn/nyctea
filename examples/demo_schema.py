"""Minimal demo schema and functions for package examples."""


import polars as pl

from nyctea.functions import FunctionRegistry
from nyctea.schema.model import Check, ColumnSchema, FrameCheck, FrameParser, Parser, SchemaModel

registry = FunctionRegistry()


@registry.column_parser(name="strip")
def strip(col: pl.Expr) -> pl.Expr:
    """Trim whitespace from a string column."""
    return col.str.strip_chars()


@registry.column_parser(name="to_int")
def to_int(col: pl.Expr) -> pl.Expr:
    """Cast a string column to Int64."""
    return col.cast(pl.Int64)


@registry.column_check(name="non_null")
def non_null(col: pl.Expr) -> pl.Expr:
    """Check that no null values are present."""
    return col.is_not_null()


@registry.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    """Check that values are strictly greater than zero."""
    return col.gt(0)


@registry.frame_parser(name="strip_strings")
def strip_strings(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Strip whitespace from all Utf8 columns."""
    schema = lf.collect_schema()
    string_cols = [pl.col(name).str.strip_chars() for name, dtype in schema.items() if dtype == pl.Utf8]
    return lf.with_columns(string_cols)


@registry.frame_check(name="no_duplicate_ids")
def no_duplicate_ids(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Raise if duplicate patient_id values exist."""
    duplicates = (
        lf.group_by("patient_id")
        .len()
        .filter(pl.col("len") > 1)
        .select("patient_id")
        .collect()
    )
    if duplicates.height > 0:
        values = duplicates.to_series(0).to_list()
        raise ValueError(f"Duplicate patient_id values: {values}")
    return lf


schema = SchemaModel(
    lazy=True,
    coerce=True,
    columns={
        "patient_id": ColumnSchema(
            dtype="Utf8",
            synonyms=["pid"],
            parsers=[Parser(name="strip")],
            checks=[Check(name="non_null")],
            required=True,
            nullable=False,
        ),
        "age_years": ColumnSchema(
            dtype="Int64",
            synonyms=["age"],
            parsers=[Parser(name="strip"), Parser(name="to_int")],
            checks=[Check(name="positive")],
            required=True,
            nullable=False,
        ),
    },
    frame_parsers=[FrameParser(name="strip_strings")],
    frame_checks=[FrameCheck(name="no_duplicate_ids")],
)
