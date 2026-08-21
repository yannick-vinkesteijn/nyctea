"""Built-in column parser plugins."""

from typing import Any

import polars as pl

from nyctea.plugins.base import ValidatorMetadata
from nyctea.plugins.column import ColumnParser

__all__ = [
    "LowerParser",
    "StripParser",
    "ToFloatParser",
    "ToIntParser",
    "UpperParser",
]


class StripParser(ColumnParser):
    """Strip whitespace from string columns."""

    def __init__(self) -> None:
        """Initialize strip parser."""
        super().__init__(
            ValidatorMetadata(
                name="strip",
                description="Remove leading and trailing whitespace",
                tags=["string", "cleaning"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Strip whitespace from column values.

        Args:
            column: Input column expression.
            **kwargs: No arguments accepted.

        Returns:
            Expression with whitespace stripped.
        """
        return column.str.strip_chars()

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments (none accepted)."""
        if kwargs:
            raise ValueError(f"strip parser does not accept arguments, got: {kwargs}")


class ToIntParser(ColumnParser):
    """Convert string column to integer."""

    def __init__(self) -> None:
        """Initialize to_int parser."""
        super().__init__(
            ValidatorMetadata(
                name="to_int",
                description="Convert string to integer (i64)",
                tags=["conversion", "numeric"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Convert column to integer.

        Args:
            column: Input column expression.
            **kwargs: No arguments accepted.

        Returns:
            Expression cast to i64.
        """
        return column.cast(pl.Int64, strict=False)

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments (none accepted)."""
        if kwargs:
            raise ValueError(f"to_int parser does not accept arguments, got: {kwargs}")


class ToFloatParser(ColumnParser):
    """Convert string column to float."""

    def __init__(self) -> None:
        """Initialize to_float parser."""
        super().__init__(
            ValidatorMetadata(
                name="to_float",
                description="Convert string to float (f64)",
                tags=["conversion", "numeric"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Convert column to float.

        Args:
            column: Input column expression.
            **kwargs: No arguments accepted.

        Returns:
            Expression cast to f64.
        """
        return column.cast(pl.Float64, strict=False)

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments (none accepted)."""
        if kwargs:
            raise ValueError(f"to_float parser does not accept arguments, got: {kwargs}")


class LowerParser(ColumnParser):
    """Convert string column to lowercase."""

    def __init__(self) -> None:
        """Initialize lower parser."""
        super().__init__(
            ValidatorMetadata(
                name="lower",
                description="Convert string to lowercase",
                tags=["string", "normalization"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Convert column to lowercase.

        Args:
            column: Input column expression.
            **kwargs: No arguments accepted.

        Returns:
            Expression with lowercase values.
        """
        return column.str.to_lowercase()

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments (none accepted)."""
        if kwargs:
            raise ValueError(f"lower parser does not accept arguments, got: {kwargs}")


class UpperParser(ColumnParser):
    """Convert string column to uppercase."""

    def __init__(self) -> None:
        """Initialize upper parser."""
        super().__init__(
            ValidatorMetadata(
                name="upper",
                description="Convert string to uppercase",
                tags=["string", "normalization"],
            )
        )

    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Convert column to uppercase.

        Args:
            column: Input column expression.
            **kwargs: No arguments accepted.

        Returns:
            Expression with uppercase values.
        """
        return column.str.to_uppercase()

    def validate_args(self, **kwargs: Any) -> None:
        """Validate arguments (none accepted)."""
        if kwargs:
            raise ValueError(f"upper parser does not accept arguments, got: {kwargs}")
