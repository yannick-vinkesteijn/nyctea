"""Built-in validators for common validation tasks.

Importing this package is what puts the built-ins in the catalogue, so
`register_builtins` has something to register. That is the one pitfall of a
decorator-declared registry, and `tests/validators/builtins/test_register.py` pins it.
"""

from nyctea.validators.builtins.checks import between, in_set, min_value, unique
from nyctea.validators.builtins.parsers import lower, strip, to_float, to_int, upper

__all__ = [
    "between",
    "in_set",
    "lower",
    "min_value",
    "strip",
    "to_float",
    "to_int",
    "unique",
    "upper",
]
