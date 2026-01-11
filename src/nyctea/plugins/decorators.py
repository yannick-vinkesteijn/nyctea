"""Decorator adapters for functional-style plugin registration.

This module provides decorators that allow functions to be registered as plugins
without explicitly creating plugin classes. This maintains the ergonomic
functional API while leveraging the OOP plugin system internally.
"""


from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import polars as pl

from nyctea.plugins.base import PluginMetadata
from nyctea.plugins.column import ColumnCheck, ColumnParser
from nyctea.plugins.frame import FrameCheck, FrameParser

if TYPE_CHECKING:
    from nyctea.plugins.registry import MasterRegistry

__all__ = [
    "PluginDecorator",
]


class PluginDecorator:
    """Decorator factory for functional-style plugin registration.

    This class provides decorators that wrap functions in anonymous plugin
    classes and register them automatically.

    Example:
        >>> from nyctea.plugins.registry import MasterRegistry
        >>> import polars as pl
        >>>
        >>> registry = MasterRegistry()
        >>> decorators = PluginDecorator(registry)
        >>>
        >>> @decorators.column_parser(name="trim")
        >>> def trim(column: pl.Expr) -> pl.Expr:
        ...     return column.str.strip_chars()
        >>>
        >>> @decorators.column_check(name="positive", tags=["numeric"])
        >>> def is_positive(column: pl.Expr) -> pl.Expr:
        ...     return column > 0
    """

    def __init__(self, registry: MasterRegistry) -> None:
        """Initialize decorator factory with a registry.

        Args:
            registry: Master registry where plugins will be registered.
        """
        self.registry = registry

    def column_parser(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        tags: Sequence[str] | None = None,
        author: str = "",
    ) -> Callable[[Callable[[pl.Expr], pl.Expr]], Callable[[pl.Expr], pl.Expr]]:
        """Decorator to register a function as a column parser.

        Args:
            name: Unique plugin name.
            description: Human-readable description.
            version: Plugin version.
            tags: Optional tags for discovery.
            author: Plugin author.

        Returns:
            Decorator function.

        Example:
            >>> @decorators.column_parser(name="uppercase")
            >>> def to_upper(column: pl.Expr) -> pl.Expr:
            ...     return column.str.to_uppercase()
        """

        def decorator(func: Callable[[pl.Expr], pl.Expr]) -> Callable[[pl.Expr], pl.Expr]:
            # Create anonymous plugin class wrapping the function
            class FunctionColumnParser(ColumnParser):
                def __init__(self) -> None:
                    metadata = PluginMetadata(
                        name=name,
                        description=description or func.__doc__ or "",
                        version=version,
                        tags=list(tags) if tags else [],
                        author=author,
                    )
                    super().__init__(metadata)

                def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
                    return func(column, **kwargs)

                def validate_args(self, **kwargs: Any) -> None:
                    # No additional validation for function-based plugins
                    pass

            # Create instance and register
            plugin = FunctionColumnParser()
            self.registry.register_column_parser(plugin)

            # Return original function for use
            return func

        return decorator

    def column_check(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        tags: Sequence[str] | None = None,
        author: str = "",
    ) -> Callable[[Callable[[pl.Expr], pl.Expr]], Callable[[pl.Expr], pl.Expr]]:
        """Decorator to register a function as a column check.

        Args:
            name: Unique plugin name.
            description: Human-readable description.
            version: Plugin version.
            tags: Optional tags for discovery.
            author: Plugin author.

        Returns:
            Decorator function.

        Example:
            >>> @decorators.column_check(name="not_empty")
            >>> def check_not_empty(column: pl.Expr) -> pl.Expr:
            ...     return column.str.len_chars() > 0
        """

        def decorator(func: Callable[[pl.Expr], pl.Expr]) -> Callable[[pl.Expr], pl.Expr]:
            # Create anonymous plugin class wrapping the function
            class FunctionColumnCheck(ColumnCheck):
                def __init__(self) -> None:
                    metadata = PluginMetadata(
                        name=name,
                        description=description or func.__doc__ or "",
                        version=version,
                        tags=list(tags) if tags else [],
                        author=author,
                    )
                    super().__init__(metadata)

                def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
                    return func(column, **kwargs)

                def validate_args(self, **kwargs: Any) -> None:
                    # No additional validation for function-based plugins
                    pass

            # Create instance and register
            plugin = FunctionColumnCheck()
            self.registry.register_column_check(plugin)

            # Return original function for use
            return func

        return decorator

    def frame_parser(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        tags: Sequence[str] | None = None,
        author: str = "",
        preserve_columns: bool = True,
        preserve_rows: bool = False,
    ) -> Callable[[Callable[[pl.LazyFrame], pl.LazyFrame]], Callable[[pl.LazyFrame], pl.LazyFrame]]:
        """Decorator to register a function as a frame parser.

        Args:
            name: Unique plugin name.
            description: Human-readable description.
            version: Plugin version.
            tags: Optional tags for discovery.
            author: Plugin author.
            preserve_columns: If True, enforce column preservation.
            preserve_rows: If True, enforce row preservation.

        Returns:
            Decorator function.

        Example:
            >>> @decorators.frame_parser(name="sort_by_age", preserve_rows=True)
            >>> def sort_age(frame: pl.LazyFrame) -> pl.LazyFrame:
            ...     return frame.sort("age")
        """

        def decorator(
            func: Callable[[pl.LazyFrame], pl.LazyFrame],
        ) -> Callable[[pl.LazyFrame], pl.LazyFrame]:
            # Create anonymous plugin class wrapping the function
            class FunctionFrameParser(FrameParser):
                def __init__(self) -> None:
                    metadata = PluginMetadata(
                        name=name,
                        description=description or func.__doc__ or "",
                        version=version,
                        tags=list(tags) if tags else [],
                        author=author,
                    )
                    super().__init__(
                        metadata,
                        preserve_columns=preserve_columns,
                        preserve_rows=preserve_rows,
                    )

                def execute(self, frame: pl.LazyFrame, **kwargs: Any) -> pl.LazyFrame:
                    return func(frame, **kwargs)

                def validate_args(self, **kwargs: Any) -> None:
                    # No additional validation for function-based plugins
                    pass

            # Create instance and register
            plugin = FunctionFrameParser()
            self.registry.register_frame_parser(plugin)

            # Return original function for use
            return func

        return decorator

    def frame_check(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        tags: Sequence[str] | None = None,
        author: str = "",
    ) -> Callable[[Callable[[pl.LazyFrame], pl.LazyFrame]], Callable[[pl.LazyFrame], pl.LazyFrame]]:
        """Decorator to register a function as a frame check.

        Args:
            name: Unique plugin name.
            description: Human-readable description.
            version: Plugin version.
            tags: Optional tags for discovery.
            author: Plugin author.

        Returns:
            Decorator function.

        Example:
            >>> @decorators.frame_check(name="min_rows")
            >>> def check_min_rows(frame: pl.LazyFrame, min_rows: int = 1) -> pl.LazyFrame:
            ...     count = frame.select(pl.len()).collect().item()
            ...     if count < min_rows:
            ...         raise ValueError(f"Expected >= {min_rows} rows, got {count}")
            ...     return frame
        """

        def decorator(
            func: Callable[[pl.LazyFrame], pl.LazyFrame],
        ) -> Callable[[pl.LazyFrame], pl.LazyFrame]:
            # Create anonymous plugin class wrapping the function
            class FunctionFrameCheck(FrameCheck):
                def __init__(self) -> None:
                    metadata = PluginMetadata(
                        name=name,
                        description=description or func.__doc__ or "",
                        version=version,
                        tags=list(tags) if tags else [],
                        author=author,
                    )
                    super().__init__(metadata)

                def execute(self, frame: pl.LazyFrame, **kwargs: Any) -> pl.LazyFrame:
                    return func(frame, **kwargs)

                def validate_args(self, **kwargs: Any) -> None:
                    # No additional validation for function-based plugins
                    pass

            # Create instance and register
            plugin = FunctionFrameCheck()
            self.registry.register_frame_check(plugin)

            # Return original function for use
            return func

        return decorator
