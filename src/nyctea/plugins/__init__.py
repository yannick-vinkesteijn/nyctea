"""Plugin system for extending Nyctea validation.

This package provides the foundation for Nyctea's plugin architecture, allowing
users to extend validation capabilities through custom parsers and checks.

Base Classes:
    - BasePlugin: Abstract base for all plugins
    - ColumnPlugin: Base for column-level operations
    - ColumnParser: Column transformations
    - ColumnCheck: Column validations
    - FramePlugin: Base for frame-level operations
    - FrameParser: Frame transformations
    - FrameCheck: Frame validations

Example:
    >>> from nyctea.plugins.column import ColumnParser
    >>> from nyctea.plugins.base import PluginMetadata
    >>> import polars as pl
    >>>
    >>> class TrimParser(ColumnParser):
    ...     def __init__(self):
    ...         super().__init__(PluginMetadata(name="trim"))
    ...
    ...     def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
    ...         return column.str.strip_chars()
    ...
    ...     def validate_args(self, **kwargs) -> None:
    ...         pass
"""

from nyctea.plugins.base import BasePlugin, PluginMetadata
from nyctea.plugins.column import ColumnCheck, ColumnParser, ColumnPlugin
from nyctea.plugins.frame import FrameCheck, FrameParser, FramePlugin

__all__ = [
    "BasePlugin",
    "PluginMetadata",
    "ColumnPlugin",
    "ColumnParser",
    "ColumnCheck",
    "FramePlugin",
    "FrameParser",
    "FrameCheck",
]
