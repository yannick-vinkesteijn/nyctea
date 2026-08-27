"""Titanic example registry with parsers and checks."""

import polars as pl

from nyctea import Registry, ValidatorDecorator

registry = Registry()
decorators = ValidatorDecorator(registry)


# Column parsers
@decorators.column_parser(name="strip")
def strip(col: pl.Expr) -> pl.Expr:
    """Trim whitespace from strings."""
    return col.str.strip_chars()


@decorators.column_parser(name="lower")
def lower(col: pl.Expr) -> pl.Expr:
    """Lowercase strings."""
    return col.str.to_lowercase()


@decorators.column_parser(name="upper")
def upper(col: pl.Expr) -> pl.Expr:
    """Uppercase strings."""
    return col.str.to_uppercase()


@decorators.column_parser(name="to_int")
def to_int(col: pl.Expr) -> pl.Expr:
    """Cast values to Int64."""
    return col.cast(pl.Int64)


@decorators.column_parser(name="to_float")
def to_float(col: pl.Expr) -> pl.Expr:
    """Cast values to Float64."""
    return col.cast(pl.Float64)


# Column checks
@decorators.column_check(name="non_null")
def non_null(col: pl.Expr) -> pl.Expr:
    """Ensure values are not null."""
    return col.is_not_null()


@decorators.column_check(name="min_zero")
def min_zero(col: pl.Expr) -> pl.Expr:
    """Ensure values are >= 0."""
    return col.ge(0)


@decorators.column_check(name="between_0_100")
def between_0_100(col: pl.Expr) -> pl.Expr:
    """Ensure values are within [0, 100]."""
    return col.is_between(0, 100)


@decorators.column_check(name="in_pclass")
def in_pclass(col: pl.Expr) -> pl.Expr:
    """Ensure Pclass is 1, 2, or 3."""
    return col.is_in([1, 2, 3])


@decorators.column_check(name="in_sex")
def in_sex(col: pl.Expr) -> pl.Expr:
    """Ensure sex is male or female."""
    return col.is_in(["male", "female"])


@decorators.column_check(name="in_embarked")
def in_embarked(col: pl.Expr) -> pl.Expr:
    """Ensure Embarked is C, Q, or S."""
    return col.is_in(["C", "Q", "S"])


@decorators.column_check(name="in_survived")
def in_survived(col: pl.Expr) -> pl.Expr:
    """Ensure Survived is 0 or 1."""
    return col.is_in([0, 1])


# Column check for uniqueness
@decorators.column_check(name="unique_passenger_id")
def unique_passenger_id(col: pl.Expr) -> pl.Expr:
    """Ensure passenger_id values are unique."""
    return col.is_unique()


# Frame-level functions
@decorators.frame_parser(name="strip_all_strings")
def strip_all_strings(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Strip whitespace from all Utf8 columns."""
    return lf.with_columns(pl.col(pl.Utf8).str.strip_chars())


__all__ = ["registry"]
