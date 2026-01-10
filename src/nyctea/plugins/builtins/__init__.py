"""Built-in plugins for common validation tasks.

This package provides a set of commonly-used parsers and checks that are
ready to use out of the box.
"""

from nyctea.plugins.builtins.parsers import (
    LowerParser,
    StripParser,
    ToFloatParser,
    ToIntParser,
    UpperParser,
)
from nyctea.plugins.builtins.checks import (
    BetweenCheck,
    InSetCheck,
    MinValueCheck,
    UniqueCheck,
)

__all__ = [
    # Parsers
    "StripParser",
    "ToIntParser",
    "ToFloatParser",
    "LowerParser",
    "UpperParser",
    # Checks
    "BetweenCheck",
    "InSetCheck",
    "MinValueCheck",
    "UniqueCheck",
]
