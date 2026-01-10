"""Built-in column check plugins."""

from typing import Any

import polars as pl

from nyctea.plugins.base import PluginMetadata
from nyctea.plugins.column import ColumnCheck

__all__ = [
    "BetweenCheck",
    "InSetCheck",
    "MinValueCheck",
    "UniqueCheck",
]


class BetweenCheck(ColumnCheck):
    """Check that values are within a range."""

    def __init__(self) -> None:
        """Initialize between check."""
        super().__init__(
            PluginMetadata(
                name="between",
                description="Check values are within min/max range (inclusive)",
                tags=["numeric", "range"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Check column values are within range.

        Args:
            column: Input column expression.
            **kwargs: Must include 'min' and 'max' arguments.

        Returns:
            Boolean expression indicating which values pass.
        """
        min_val = kwargs["min"]
        max_val = kwargs["max"]
        return column.is_between(min_val, max_val, closed="both")

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments."""
        if "min" not in kwargs:
            raise ValueError("between check requires 'min' argument")
        if "max" not in kwargs:
            raise ValueError("between check requires 'max' argument")
        if not isinstance(kwargs["min"], (int, float)):
            raise TypeError("min must be numeric")
        if not isinstance(kwargs["max"], (int, float)):
            raise TypeError("max must be numeric")
        if kwargs["min"] > kwargs["max"]:
            raise ValueError("min must be <= max")


class InSetCheck(ColumnCheck):
    """Check that values are in a set of allowed values."""

    def __init__(self) -> None:
        """Initialize in_set check."""
        super().__init__(
            PluginMetadata(
                name="in_set",
                description="Check values are in allowed set",
                tags=["categorical", "validation"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Check column values are in allowed set.

        Args:
            column: Input column expression.
            **kwargs: Must include 'values' argument.

        Returns:
            Boolean expression indicating which values pass.
        """
        allowed = kwargs["values"]
        return column.is_in(allowed)

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments."""
        if "values" not in kwargs:
            raise ValueError("in_set check requires 'values' argument")
        if not isinstance(kwargs["values"], (list, tuple, set)):
            raise TypeError("values must be a list, tuple, or set")
        if len(kwargs["values"]) == 0:
            raise ValueError("values cannot be empty")


class MinValueCheck(ColumnCheck):
    """Check that values are >= minimum."""

    def __init__(self) -> None:
        """Initialize min_value check."""
        super().__init__(
            PluginMetadata(
                name="min_value",
                description="Check values are >= minimum",
                tags=["numeric", "range"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Check column values are >= minimum.

        Args:
            column: Input column expression.
            **kwargs: Must include 'min' argument.

        Returns:
            Boolean expression indicating which values pass.
        """
        min_val = kwargs["min"]
        return column >= min_val

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments."""
        if "min" not in kwargs:
            raise ValueError("min_value check requires 'min' argument")
        if not isinstance(kwargs["min"], (int, float)):
            raise TypeError("min must be numeric")


class UniqueCheck(ColumnCheck):
    """Check that all values in column are unique."""

    def __init__(self) -> None:
        """Initialize unique check."""
        super().__init__(
            PluginMetadata(
                name="unique",
                description="Check all values are unique (no duplicates)",
                tags=["uniqueness", "validation"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Check column values are unique.

        Args:
            column: Input column expression.
            **kwargs: No arguments accepted.

        Returns:
            Boolean expression indicating which values pass.
        """
        # For each value, check if count > 1 (is duplicate)
        # Return True for non-duplicates
        return ~column.is_duplicated()

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments (none accepted)."""
        if kwargs:
            raise ValueError(f"unique check does not accept arguments, got: {kwargs}")
