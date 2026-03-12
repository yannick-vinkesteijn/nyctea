"""Plugin system for extending Nyctea validation.

This package provides the foundation for Nyctea's plugin architecture, allowing
users to extend validation capabilities through custom parsers and checks.

Base Classes:
    - Validator: Abstract base for all validators
    - ColumnPlugin: Base for column-level operations
    - ColumnParser: Column transformations
    - ColumnCheck: Column validations
    - FramePlugin: Base for frame-level operations
    - FrameParser: Frame transformations
    - FrameCheck: Frame validations

Example:
    >>> from nyctea.plugins.column import ColumnParser
    >>> from nyctea.plugins.base import ValidatorMetadata
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

from nyctea.plugins.base import Validator, ValidatorMetadata
from nyctea.plugins.column import ColumnCheck, ColumnParser, ColumnPlugin
from nyctea.plugins.frame import FrameCheck, FrameParser, FramePlugin

__all__ = [
    "Validator",
    "ValidatorMetadata",
    "ColumnPlugin",
    "ColumnParser",
    "ColumnCheck",
    "FramePlugin",
    "FrameParser",
    "FrameCheck",
]
