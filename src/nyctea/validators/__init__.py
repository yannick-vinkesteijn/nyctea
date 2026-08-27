"""Validator system for extending Nyctea validation.

This package provides the foundation for Nyctea's validator architecture, allowing
users to extend validation capabilities through custom parsers and checks.

Base Classes:
    - Validator: Abstract base for all validators
    - ColumnValidator: Base for column-level operations
    - ColumnParser: Column transformations
    - ColumnCheck: Column validations
    - FrameValidator: Base for frame-level operations
    - FrameParser: Frame transformations
    - FrameCheck: Frame validations

Example:
    >>> from nyctea.validators.column import ColumnParser
    >>> from nyctea.validators.base import ValidatorMetadata
    >>> import polars as pl
    >>>
    >>> class TrimParser(ColumnParser):
    ...     def __init__(self):
    ...         super().__init__(ValidatorMetadata(name="trim"))
    ...
    ...     def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
    ...         return column.str.strip_chars()
    ...
    ...     def validate_args(self, **kwargs) -> None:
    ...         pass
"""

from nyctea.validators.base import Validator, ValidatorMetadata
from nyctea.validators.builtins.register import register_builtins
from nyctea.validators.column import ColumnCheck, ColumnParser, ColumnValidator
from nyctea.validators.decorators import ValidatorDecorator
from nyctea.validators.frame import FrameCheck, FrameParser, FrameValidator
from nyctea.validators.registry import Registry, ValidatorRegistry

__all__ = [
    "ColumnCheck",
    "ColumnParser",
    "ColumnValidator",
    "FrameCheck",
    "FrameParser",
    "FrameValidator",
    "Registry",
    "Validator",
    "ValidatorDecorator",
    "ValidatorMetadata",
    "ValidatorRegistry",
    "register_builtins",
]
