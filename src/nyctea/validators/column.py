"""Column-level validator classes with purity enforcement.

This module provides base classes for column-level operations (parsers and checks)
with strict enforcement of single-column purity - validators can only reference
the input column and cannot access other columns in the DataFrame.
"""

import inspect
from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from nyctea.exceptions import RegistrationError, ValidatorExecutionError
from nyctea.validators.base import Validator, ValidatorMetadata

__all__ = [
    "ColumnCheck",
    "ColumnParser",
    "ColumnValidator",
]


class ColumnValidator(Validator[pl.Expr, pl.Expr], ABC):
    """Abstract base class for all column-level validators.

    Column validators operate on a single column (Polars expression) and must
    maintain "column purity" - they can only reference the input column
    and cannot access other columns in the DataFrame.

    This base class enforces purity through runtime validation in the __call__
    method by checking the column references in both input and output expressions.

    Subclasses must implement:
    - execute(column: pl.Expr, **kwargs) -> pl.Expr
    - validate_args(**kwargs) -> None
    """

    def __init__(self, metadata: ValidatorMetadata) -> None:
        """Initialize column validator with metadata.

        Args:
            metadata: Validator metadata.

        Raises:
            RegistrationError: If the execute() method signature is invalid.
        """
        super().__init__(metadata)
        self._validate_signature()

    @abstractmethod
    def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:  # ty: ignore[invalid-method-override]
        """Execute the validator logic on a single column expression.

        Args:
            column: The input column expression.
            **kwargs: Validator-specific arguments.

        Returns:
            Transformed or validated column expression.
        """

    def _validate_signature(self) -> None:
        """Validate that execute() has correct signature.

        The execute() method must:
        - Have 'column' as the first parameter
        - Accept **kwargs for additional arguments
        - Return pl.Expr

        Raises:
            RegistrationError: If signature validation fails.
        """
        try:
            sig = inspect.signature(self.execute, eval_str=True)
        except NameError as e:
            raise RegistrationError(
                f"Validator '{self.name}' execute() has an unresolvable annotation: {e}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
            ) from e
        params = list(sig.parameters.values())

        # Skip 'self' parameter
        if params and params[0].name == "self":
            params = params[1:]

        # Check first parameter
        if not params or params[0].name != "column":
            raise RegistrationError(
                f"Validator '{self.name}' execute() must have 'column' as first parameter",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
            )

        # Check that parameter is annotated as pl.Expr
        first_param = params[0]
        if first_param.annotation not in (pl.Expr, inspect.Parameter.empty):
            raise RegistrationError(
                f"Validator '{self.name}' execute() 'column' parameter must be "
                f"annotated as pl.Expr, got {first_param.annotation}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
            )

    def _validate_purity(self, expr: pl.Expr, context: str) -> None:
        """Validate that expression references exactly one column.

        Args:
            expr: Expression to validate.
            context: Context description for error messages ("input" or "output").

        Raises:
            ValidatorExecutionError: If expression references multiple columns.
        """
        try:
            # Get root column names referenced by this expression
            root_names = expr.meta.root_names()

            if len(root_names) == 0:
                raise ValidatorExecutionError(
                    f"Validator '{self.name}' {context} expression references no columns. "
                    "Column validators must reference exactly one column.",
                    validator_name=self.name,
                    validator_type=self.__class__.__name__,
                )

            if len(root_names) > 1:
                raise ValidatorExecutionError(
                    f"Validator '{self.name}' {context} expression references multiple "
                    f"columns: {root_names}. Column validators must only reference "
                    "the input column (single-column purity).",
                    validator_name=self.name,
                    validator_type=self.__class__.__name__,
                )
        except Exception as e:
            if isinstance(e, ValidatorExecutionError):
                raise
            # If meta.root_names() fails for any reason, raise an error
            raise ValidatorExecutionError(
                f"Validator '{self.name}' failed to validate {context} expression: {e}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
                original_error=e,
            ) from e

    def __call__(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:  # ty: ignore[invalid-method-override]
        """Execute validator with purity validation.

        This method wraps execute() to enforce column purity constraints.
        It validates that both input and output expressions reference exactly
        one column, and that they reference the same column.

        Args:
            column: Input column expression.
            **kwargs: Validator-specific arguments.

        Returns:
            Output column expression.

        Raises:
            ValidatorExecutionError: If purity validation fails.
            TypeError: If column is not a Polars expression.
        """
        # Type check
        if not isinstance(column, pl.Expr):
            raise TypeError(f"Validator '{self.name}' expected pl.Expr, got {type(column).__name__}")

        # Validate input purity
        self._validate_purity(column, "input")
        input_column = column.meta.root_names()[0]

        # Validate arguments
        self.validate_args(**kwargs)

        # Execute validator
        try:
            result = self.execute(column, **kwargs)
        except Exception as e:
            raise ValidatorExecutionError(
                f"Validator '{self.name}' execution failed: {e}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
                column=input_column,
                original_error=e,
            ) from e

        # Type check output
        if not isinstance(result, pl.Expr):
            raise ValidatorExecutionError(
                f"Validator '{self.name}' must return pl.Expr, got {type(result).__name__}",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
                column=input_column,
            )

        # Validate output purity
        self._validate_purity(result, "output")
        output_column = result.meta.root_names()[0]

        # Ensure input and output reference the same column
        if input_column != output_column:
            raise ValidatorExecutionError(
                f"Validator '{self.name}' violated purity constraint: "
                f"input references '{input_column}' but output references "
                f"'{output_column}'. Column validators must preserve the column reference.",
                validator_name=self.name,
                validator_type=self.__class__.__name__,
                column=input_column,
            )

        return result


class ColumnParser(ColumnValidator):
    """Base class for column parsers (transformations).

    Column parsers transform column values while maintaining the column structure.
    Common examples: trim whitespace, convert case, parse dates, clean strings.

    Parsers are executed before type coercion and checks in the validation pipeline.

    Example:
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
        ...         pass  # No args to validate
    """


class ColumnCheck(ColumnValidator):
    """Base class for column checks (validations).

    Column checks validate column values and return a boolean expression
    indicating which rows pass validation.

    Checks are executed after parsing and type coercion in the validation pipeline.

    Example:
        >>> from nyctea.validators.base import ValidatorMetadata
        >>> import polars as pl
        >>>
        >>> class PositiveCheck(ColumnCheck):
        ...     def __init__(self):
        ...         super().__init__(ValidatorMetadata(name="positive"))
        ...
        ...     def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        ...         return column > 0
        ...
        ...     def validate_args(self, **kwargs) -> None:
        ...         pass  # No args to validate
    """
