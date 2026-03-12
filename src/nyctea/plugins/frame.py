"""Frame-level plugin classes with shape preservation.

This module provides base classes for frame-level operations (parsers and checks)
with configurable enforcement of shape preservation constraints.
"""


from __future__ import annotations

import inspect
from abc import ABC
from typing import TYPE_CHECKING, Any

import polars as pl

from nyctea.exceptions import ValidatorExecutionError, RegistrationError
from nyctea.plugins.base import Validator, ValidatorMetadata

if TYPE_CHECKING:
    pass

__all__ = [
    "FramePlugin",
    "FrameParser",
    "FrameCheck",
]


class FramePlugin(Validator[pl.LazyFrame, pl.LazyFrame], ABC):
    """Abstract base class for all frame-level plugins.

    Frame plugins operate on entire DataFrames and can optionally enforce
    shape preservation constraints:
    - preserve_columns: Output must have the same columns as input
    - preserve_rows: Output must have the same number of rows as input

    Shape validation is performed at runtime in the __call__ method.

    Subclasses must implement:
    - execute(frame: pl.LazyFrame, **kwargs) -> pl.LazyFrame
    - validate_args(**kwargs) -> None

    Attributes:
        preserve_columns: If True, validates output has same columns as input.
        preserve_rows: If True, validates output has same row count as input.
    """

    def __init__(
        self,
        metadata: ValidatorMetadata,
        *,
        preserve_columns: bool = True,
        preserve_rows: bool = True,
    ) -> None:
        """Initialize frame plugin with metadata and constraints.

        Args:
            metadata: Plugin metadata.
            preserve_columns: If True, enforce column preservation.
            preserve_rows: If True, enforce row count preservation.

        Raises:
            RegistrationError: If the execute() method signature is invalid.
        """
        super().__init__(metadata)
        self.preserve_columns = preserve_columns
        self.preserve_rows = preserve_rows
        self._validate_signature()

    def _validate_signature(self) -> None:
        """Validate that execute() has correct signature.

        The execute() method must:
        - Have 'frame' as the first parameter
        - Accept **kwargs for additional arguments
        - Return pl.LazyFrame

        Raises:
            RegistrationError: If signature validation fails.
        """
        sig = inspect.signature(self.execute)
        params = list(sig.parameters.values())

        # Skip 'self' parameter
        if params and params[0].name == "self":
            params = params[1:]

        # Check first parameter
        if not params or params[0].name != "frame":
            raise RegistrationError(
                f"Plugin '{self.name}' execute() must have 'frame' as first parameter",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
            )

        # Check that parameter is annotated as pl.LazyFrame
        first_param = params[0]
        if first_param.annotation not in (pl.LazyFrame, inspect.Parameter.empty):
            raise RegistrationError(
                f"Plugin '{self.name}' execute() 'frame' parameter must be "
                f"annotated as pl.LazyFrame, got {first_param.annotation}",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
            )

    def __call__(self, frame: pl.LazyFrame, **kwargs: Any) -> pl.LazyFrame:
        """Execute plugin with shape validation.

        This method wraps execute() to enforce shape preservation constraints
        if configured.

        Args:
            frame: Input LazyFrame.
            **kwargs: Plugin-specific arguments.

        Returns:
            Output LazyFrame.

        Raises:
            ValidatorExecutionError: If shape validation fails.
            TypeError: If frame is not a LazyFrame.
        """
        # Type check
        if not isinstance(frame, pl.LazyFrame):
            raise TypeError(
                f"Plugin '{self.name}' expected pl.LazyFrame, "
                f"got {type(frame).__name__}"
            )

        # Capture input shape for validation
        input_columns = frame.collect_schema().names() if self.preserve_columns else None
        input_row_count = None
        if self.preserve_rows:
            # We need to collect to get row count - this is a performance trade-off
            # Only do this if preserve_rows is True
            input_row_count = frame.select(pl.len()).collect().item()

        # Validate arguments
        self.validate_args(**kwargs)

        # Execute plugin
        try:
            result = self.execute(frame, **kwargs)
        except Exception as e:
            raise ValidatorExecutionError(
                f"Plugin '{self.name}' execution failed: {e}",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
                original_error=e,
            ) from e

        # Type check output
        if not isinstance(result, pl.LazyFrame):
            raise ValidatorExecutionError(
                f"Plugin '{self.name}' must return pl.LazyFrame, "
                f"got {type(result).__name__}",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
            )

        # Validate column preservation
        if self.preserve_columns:
            output_columns = result.collect_schema().names()
            if set(output_columns) != set(input_columns):
                missing = set(input_columns) - set(output_columns)
                extra = set(output_columns) - set(input_columns)
                error_parts = []
                if missing:
                    error_parts.append(f"missing columns: {sorted(missing)}")
                if extra:
                    error_parts.append(f"extra columns: {sorted(extra)}")
                raise ValidatorExecutionError(
                    f"Plugin '{self.name}' violated column preservation: "
                    f"{', '.join(error_parts)}",
                    plugin_name=self.name,
                    plugin_type=self.__class__.__name__,
                )

        # Validate row count preservation
        if self.preserve_rows and input_row_count is not None:
            output_row_count = result.select(pl.len()).collect().item()
            if output_row_count != input_row_count:
                raise ValidatorExecutionError(
                    f"Plugin '{self.name}' violated row preservation: "
                    f"input had {input_row_count} rows, output has {output_row_count}",
                    plugin_name=self.name,
                    plugin_type=self.__class__.__name__,
                )

        return result


class FrameParser(FramePlugin):
    """Base class for frame parsers (transformations).

    Frame parsers transform entire DataFrames. Common examples: add computed
    columns, reorder rows, deduplicate, filter rows.

    By default, frame parsers preserve columns but may modify rows.
    This can be configured via preserve_columns and preserve_rows flags.

    Example:
        >>> from nyctea.plugins.base import ValidatorMetadata
        >>> import polars as pl
        >>>
        >>> class DeduplicateParser(FrameParser):
        ...     def __init__(self):
        ...         super().__init__(
        ...             ValidatorMetadata(name="deduplicate"),
        ...             preserve_columns=True,
        ...             preserve_rows=False  # Dedup may remove rows
        ...         )
        ...
        ...     def execute(self, frame: pl.LazyFrame, **kwargs) -> pl.LazyFrame:
        ...         return frame.unique()
        ...
        ...     def validate_args(self, **kwargs) -> None:
        ...         pass
    """

    def __init__(
        self,
        metadata: ValidatorMetadata,
        *,
        preserve_columns: bool = True,
        preserve_rows: bool = False,  # Parsers may modify row count
    ) -> None:
        """Initialize frame parser.

        Args:
            metadata: Plugin metadata.
            preserve_columns: If True, enforce column preservation (default: True).
            preserve_rows: If True, enforce row preservation (default: False).
        """
        super().__init__(
            metadata,
            preserve_columns=preserve_columns,
            preserve_rows=preserve_rows,
        )


class FrameCheck(FramePlugin):
    """Base class for frame checks (validations).

    Frame checks validate entire DataFrames and return a boolean expression
    or raise an exception on failure.

    Frame checks always preserve both columns and rows.

    Example:
        >>> from nyctea.plugins.base import ValidatorMetadata
        >>> import polars as pl
        >>>
        >>> class MinRowsCheck(FrameCheck):
        ...     def __init__(self):
        ...         super().__init__(ValidatorMetadata(name="min_rows"))
        ...
        ...     def execute(self, frame: pl.LazyFrame, **kwargs) -> pl.LazyFrame:
        ...         min_rows = kwargs.get("min_rows", 1)
        ...         row_count = frame.select(pl.len()).collect().item()
        ...         if row_count < min_rows:
        ...             raise ValueError(f"Expected >= {min_rows} rows, got {row_count}")
        ...         return frame
        ...
        ...     def validate_args(self, **kwargs) -> None:
        ...         if "min_rows" in kwargs:
        ...             if not isinstance(kwargs["min_rows"], int):
        ...                 raise TypeError("min_rows must be int")
        ...             if kwargs["min_rows"] < 0:
        ...                 raise ValueError("min_rows must be >= 0")
    """

    def __init__(self, metadata: ValidatorMetadata) -> None:
        """Initialize frame check.

        Frame checks always preserve both columns and rows.

        Args:
            metadata: Plugin metadata.
        """
        super().__init__(
            metadata,
            preserve_columns=True,
            preserve_rows=True,
        )
