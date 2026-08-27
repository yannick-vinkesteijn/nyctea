"""Helper functions to register built-in validators."""

from nyctea.validators.builtins.checks import (
    BetweenCheck,
    InSetCheck,
    MinValueCheck,
    UniqueCheck,
)
from nyctea.validators.builtins.parsers import (
    LowerParser,
    StripParser,
    ToFloatParser,
    ToIntParser,
    UpperParser,
)
from nyctea.validators.registry import Registry

__all__ = ["register_builtins"]


def register_builtins(registry: Registry) -> None:
    """Register all built-in validators.

    Args:
        registry: Master registry to register validators in.

    Example:
        >>> from nyctea.validators.registry import Registry
        >>> from nyctea.validators.builtins.register import register_builtins
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
