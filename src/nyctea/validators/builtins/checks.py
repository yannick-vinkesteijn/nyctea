"""Built-in column checks.

Each is the expression it evaluates plus the arguments it declares. The keyword-only
parameters are the contract, so a missing or misspelled schema argument is caught by
binding the signature rather than by a hand-written `validate_args`.

Parameter names are the names a schema writes, which is why `min` and `max` shadow
builtins here.
"""

import polars as pl

from nyctea.validators.decorators import checker

__all__ = ["between", "in_set", "min_value", "unique"]


@checker(name="between", description="Check values are within min/max range (inclusive)", tags=["numeric", "range"])
def between(column: pl.Expr, *, min: float, max: float) -> pl.Expr:  # noqa: A002
    """Values fall within an inclusive range."""
    if min > max:
        raise ValueError(f"between requires min <= max, got min={min} and max={max}")
    return column.is_between(min, max, closed="both")


@checker(name="in_set", description="Check values are in allowed set", tags=["categorical", "validation"])
def in_set(column: pl.Expr, *, values: list[object] | tuple[object, ...] | set[object]) -> pl.Expr:
    """Values are drawn from an allowed set."""
    if not values:
        raise ValueError("in_set requires a non-empty 'values' argument")
    return column.is_in(values)


@checker(name="min_value", description="Check values are >= minimum", tags=["numeric", "range"])
def min_value(column: pl.Expr, *, min: float) -> pl.Expr:  # noqa: A002
    """Values are at or above a minimum."""
    return column >= min


@checker(name="unique", description="Check all values are unique (no duplicates)", tags=["uniqueness", "validation"])
def unique(column: pl.Expr) -> pl.Expr:
    """Values are not duplicated."""
    return ~column.is_duplicated()
