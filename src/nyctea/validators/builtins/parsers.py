"""Built-in column parsers.

Each is the expression it applies. None takes arguments, which the empty signature
after `column` states, so a schema passing one is rejected by binding rather than by a
hand-written check.
"""

import polars as pl

from nyctea.validators.decorators import parser

__all__ = ["lower", "strip", "to_float", "to_int", "upper"]


@parser(name="strip", description="Remove leading and trailing whitespace", tags=["string", "cleaning"])
def strip(column: pl.Expr) -> pl.Expr:
    """Leading and trailing whitespace removed."""
    return column.str.strip_chars()


@parser(name="to_int", description="Convert string to integer (i64)", tags=["conversion", "numeric"])
def to_int(column: pl.Expr) -> pl.Expr:
    """Cast to Int64, leaving unparsable values null."""
    return column.cast(pl.Int64, strict=False)


@parser(name="to_float", description="Convert string to float (f64)", tags=["conversion", "numeric"])
def to_float(column: pl.Expr) -> pl.Expr:
    """Cast to Float64, leaving unparsable values null."""
    return column.cast(pl.Float64, strict=False)


@parser(name="lower", description="Convert string to lowercase", tags=["string", "normalization"])
def lower(column: pl.Expr) -> pl.Expr:
    """Lowercased."""
    return column.str.to_lowercase()


@parser(name="upper", description="Convert string to uppercase", tags=["string", "normalization"])
def upper(column: pl.Expr) -> pl.Expr:
    """Uppercased."""
    return column.str.to_uppercase()
