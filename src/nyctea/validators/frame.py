"""Frame-level validator classes with shape preservation.

This module provides base classes for frame-level operations (parsers and checks)
with configurable enforcement of shape preservation constraints.
"""

import inspect
from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from nyctea.exceptions import RegistrationError, ValidatorExecutionError
from nyctea.validators.base import Validator, ValidatorMetadata

__all__ = [
    "FrameCheck",
    "FrameParser",
    "FrameValidator",
]


class FrameValidator(Validator[pl.LazyFrame, pl.LazyFrame], ABC):
    """Abstract base class for all frame-level validators.

    Frame validators operate on entire DataFrames and can optionally enforce
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
        """Initialize frame validator with metadata and constraints.

        Args:
            metadata: Validator metadata.
            preserve_columns: If True, enforce column preservation.
            preserve_rows: If True, enforce row count preservation.

        Raises:
            RegistrationError: If the execute() method signature is invalid.
        """
        super().__init__(metadata)
        self.preserve_columns = preserve_columns
        self.preserve_rows = preserve_rows
        self._validate_signature()

    @abstractmethod
    def execute(self, frame: pl.LazyFrame, **kwargs: Any) -> pl.LazyFrame:  # ty: ignore[invalid-method-override]
        """Execute the validator logic on a LazyFrame.

        Args:
            frame: The input LazyFrame.
            **kwargs: Validator-specific arguments.

        Returns:
            Transformed LazyFrame.
        """

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
                f"Validator '{self.name}' execute() must have 'frame' as first parameter",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
            )

        # Check that parameter is annotated as pl.LazyFrame
        first_param = params[0]
        if first_param.annotation not in (pl.LazyFrame, inspect.Parameter.empty):
            raise RegistrationError(
                f"Validator '{self.name}' execute() 'frame' parameter must be "
                f"annotated as pl.LazyFrame, got {first_param.annotation}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
            )

    def __call__(self, frame: pl.LazyFrame, **kwargs: Any) -> pl.LazyFrame:  # ty: ignore[invalid-method-override]  # noqa: C901
        """Execute validator with shape validation.

        This method wraps execute() to enforce shape preservation constraints
        if configured.

        Args:
            frame: Input LazyFrame.
            **kwargs: Validator-specific arguments.

        Returns:
            Output LazyFrame.

        Raises:
            ValidatorExecutionError: If shape validation fails.
            TypeError: If frame is not a LazyFrame.
        """
        # Type check
        if not isinstance(frame, pl.LazyFrame):
            raise TypeError(f"Validator '{self.name}' expected pl.LazyFrame, got {type(frame).__name__}")

        # Capture input shape for validation
        input_columns = frame.collect_schema().names() if self.preserve_columns else None
        input_row_count = None
        if self.preserve_rows:
            # We need to collect to get row count - this is a performance trade-off
            # Only do this if preserve_rows is True
            _count = frame.select(pl.len()).collect()
            assert isinstance(_count, pl.DataFrame)
            input_row_count = _count[0, 0]

        # Validate arguments
        self.validate_args(**kwargs)

        # Execute validator
        try:
            result = self.execute(frame, **kwargs)
        except Exception as e:
            raise ValidatorExecutionError(
                f"Validator '{self.name}' execution failed: {e}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
                original_error=e,
            ) from e

        # Type check output
        if not isinstance(result, pl.LazyFrame):
            raise ValidatorExecutionError(
                f"Validator '{self.name}' must return pl.LazyFrame, got {type(result).__name__}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
            )

        # Validate column preservation
        if self.preserve_columns:
            assert input_columns is not None
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
                    f"Validator '{self.name}' violated column preservation: {', '.join(error_parts)}",
                    validator_name=self.name,
                    validator_type=self.__class__.__name__,
                )

        # Validate row count preservation
        if self.preserve_rows and input_row_count is not None:
            _out_count = result.select(pl.len()).collect()
            assert isinstance(_out_count, pl.DataFrame)
            output_row_count = _out_count[0, 0]
            if output_row_count != input_row_count:
                raise ValidatorExecutionError(
                    f"Validator '{self.name}' violated row preservation: "
                    f"input had {input_row_count} rows, output has {output_row_count}",
                    validator_name=self.name,
                    validator_type=self.__class__.__name__,
                )

        return result


class FrameParser(FrameValidator):
    """Base class for frame parsers (transformations).

    Frame parsers transform entire DataFrames. Common examples: add computed
    columns, reorder rows, deduplicate, filter rows.

    By default, frame parsers preserve columns but may modify rows.
    This can be configured via preserve_columns and preserve_rows flags.

    Example:
        >>> from nyctea.validators.base import ValidatorMetadata
        >>> import polars as pl
        >>>
        >>> class DeduplicateParser(FrameParser):
        ...     def __init__(self):
        ...         super().__init__(
        ...             ValidatorMetadata(name="deduplicate"),
        ...             preserve_columns=True,
        ...             preserve_rows=False,  # Dedup may remove rows
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
            metadata: Validator metadata.
            preserve_columns: If True, enforce column preservation (default: True).
            preserve_rows: If True, enforce row preservation (default: False).
        """
        super().__init__(
            metadata,
            preserve_columns=preserve_columns,
            preserve_rows=preserve_rows,
        )


class FrameCheck(FrameValidator):
    """Base class for frame checks (validations).

    Frame checks validate entire DataFrames and return a boolean expression
    or raise an exception on failure.

    Frame checks always preserve both columns and rows.

    Example:
        >>> from nyctea.validators.base import ValidatorMetadata
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
            metadata: Validator metadata.
        """
        super().__init__(
            metadata,
            preserve_columns=True,
            preserve_rows=True,
        )
