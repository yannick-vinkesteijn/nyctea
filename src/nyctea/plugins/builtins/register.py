"""Helper functions to register built-in plugins."""

from nyctea.plugins.builtins.checks import (
    BetweenCheck,
    InSetCheck,
    MinValueCheck,
    UniqueCheck,
)
from nyctea.plugins.builtins.parsers import (
    LowerParser,
    StripParser,
    ToFloatParser,
    ToIntParser,
    UpperParser,
)
from nyctea.plugins.registry import Registry

__all__ = ["register_builtins", "register_titanic_plugins"]


def register_builtins(registry: Registry) -> None:
    """Register all built-in plugins.

    Args:
        registry: Master registry to register plugins in.

    Example:
        >>> from nyctea.plugins.registry import Registry
        >>> from nyctea.plugins.builtins.register import register_builtins
        >>> registry = Registry()
        >>> register_builtins(registry)
    """
    # Register parsers
    registry.register_column_parser(StripParser())
    registry.register_column_parser(ToIntParser())
    registry.register_column_parser(ToFloatParser())
    registry.register_column_parser(LowerParser())
    registry.register_column_parser(UpperParser())

    # Register checks
    registry.register_column_check(BetweenCheck())
    registry.register_column_check(InSetCheck())
    registry.register_column_check(MinValueCheck())
    registry.register_column_check(UniqueCheck())


def register_titanic_plugins(registry: Registry) -> None:
    """Register plugins needed for the Titanic example.

    This registers the built-in plugins plus Titanic-specific checks.

    Args:
        registry: Master registry to register plugins in.

    Example:
        >>> from nyctea.plugins.registry import Registry
        >>> from nyctea.plugins.builtins.register import register_titanic_plugins
        >>> registry = Registry()
        >>> register_titanic_plugins(registry)
    """
    # Register all builtins first
    register_builtins(registry)

    # Import decorator for functional-style plugins
    from nyctea.plugins.decorators import ValidatorDecorator
    import polars as pl

    decorators = ValidatorDecorator(registry)

    # Titanic-specific checks using decorators
    @decorators.column_check(
        name="unique_passenger_id",
        description="Check passenger_id is unique",
    )
    def unique_passenger_id(column: pl.Expr) -> pl.Expr:
        return ~column.is_duplicated()

    @decorators.column_check(
        name="in_survived",
        description="Check survived is 0 or 1",
    )
    def in_survived(column: pl.Expr) -> pl.Expr:
        return column.is_in([0, 1])

    @decorators.column_check(
        name="in_pclass",
        description="Check pclass is 1, 2, or 3",
    )
    def in_pclass(column: pl.Expr) -> pl.Expr:
        return column.is_in([1, 2, 3])

    @decorators.column_check(
        name="in_sex",
        description="Check sex is male or female",
    )
    def in_sex(column: pl.Expr) -> pl.Expr:
        return column.is_in(["male", "female"])

    @decorators.column_check(
        name="between_0_100",
        description="Check age is between 0 and 100",
    )
    def between_0_100(column: pl.Expr) -> pl.Expr:
        return column.is_between(0, 100, closed="both")

    @decorators.column_check(
        name="min_zero",
        description="Check value is >= 0",
    )
    def min_zero(column: pl.Expr) -> pl.Expr:
        return column >= 0

    @decorators.column_check(
        name="in_embarked",
        description="Check embarked is C, Q, or S",
    )
    def in_embarked(column: pl.Expr) -> pl.Expr:
        return column.is_in(["C", "Q", "S"])
