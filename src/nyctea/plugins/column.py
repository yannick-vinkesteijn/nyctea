"""Column-level plugin classes with purity enforcement.

This module provides base classes for column-level operations (parsers and checks)
with strict enforcement of single-column purity - plugins can only reference
the input column and cannot access other columns in the DataFrame.
"""


import inspect
from abc import ABC
from typing import TYPE_CHECKING, Any

import polars as pl

from nyctea.exceptions import PluginExecutionError, RegistrationError
from nyctea.plugins.base import BasePlugin, PluginMetadata

if TYPE_CHECKING:
    pass

__all__ = [
    "ColumnPlugin",
    "ColumnParser",
    "ColumnCheck",
]


class ColumnPlugin(BasePlugin[pl.Expr, pl.Expr], ABC):
    """Abstract base class for all column-level plugins.

    Column plugins operate on a single column (Polars expression) and must
    maintain "column purity" - they can only reference the input column
    and cannot access other columns in the DataFrame.

    This base class enforces purity through runtime validation in the __call__
    method by checking the column references in both input and output expressions.

    Subclasses must implement:
    - execute(column: pl.Expr, **kwargs) -> pl.Expr
    - validate_args(**kwargs) -> None
    """

    def __init__(self, metadata: PluginMetadata) -> None:
        """Initialize column plugin with metadata.

        Args:
            metadata: Plugin metadata.

        Raises:
            RegistrationError: If the execute() method signature is invalid.
        """
        super().__init__(metadata)
        self._validate_signature()

    def _validate_signature(self) -> None:
        """Validate that execute() has correct signature.

        The execute() method must:
        - Have 'column' as the first parameter
        - Accept **kwargs for additional arguments
        - Return pl.Expr

        Raises:
            RegistrationError: If signature validation fails.
        """
        sig = inspect.signature(self.execute)
        params = list(sig.parameters.values())

        # Skip 'self' parameter
        if params and params[0].name == "self":
            params = params[1:]

        # Check first parameter
        if not params or params[0].name != "column":
            raise RegistrationError(
                f"Plugin '{self.name}' execute() must have 'column' as first parameter",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
            )

        # Check that parameter is annotated as pl.Expr
        first_param = params[0]
        if first_param.annotation not in (pl.Expr, inspect.Parameter.empty):
            raise RegistrationError(
                f"Plugin '{self.name}' execute() 'column' parameter must be "
                f"annotated as pl.Expr, got {first_param.annotation}",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
            )

    def _validate_purity(self, expr: pl.Expr, context: str) -> None:
        """Validate that expression references exactly one column.

        Args:
            expr: Expression to validate.
            context: Context description for error messages ("input" or "output").

        Raises:
            PluginExecutionError: If expression references multiple columns.
        """
        try:
            # Get root column names referenced by this expression
            root_names = expr.meta.root_names()

            if len(root_names) == 0:
                raise PluginExecutionError(
                    f"Plugin '{self.name}' {context} expression references no columns. "
                    "Column plugins must reference exactly one column.",
                    plugin_name=self.name,
                    plugin_type=self.__class__.__name__,
                )

            if len(root_names) > 1:
                raise PluginExecutionError(
                    f"Plugin '{self.name}' {context} expression references multiple "
                    f"columns: {root_names}. Column plugins must only reference "
                    "the input column (single-column purity).",
                    plugin_name=self.name,
                    plugin_type=self.__class__.__name__,
                )
        except Exception as e:
            if isinstance(e, PluginExecutionError):
                raise
            # If meta.root_names() fails for any reason, raise an error
            raise PluginExecutionError(
                f"Plugin '{self.name}' failed to validate {context} expression: {e}",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
                original_error=e,
            ) from e

    def __call__(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:
        """Execute plugin with purity validation.

        This method wraps execute() to enforce column purity constraints.
        It validates that both input and output expressions reference exactly
        one column, and that they reference the same column.

        Args:
            column: Input column expression.
            **kwargs: Plugin-specific arguments.

        Returns:
            Output column expression.

        Raises:
            PluginExecutionError: If purity validation fails.
            TypeError: If column is not a Polars expression.
        """
        # Type check
        if not isinstance(column, pl.Expr):
            raise TypeError(
                f"Plugin '{self.name}' expected pl.Expr, got {type(column).__name__}"
            )

        # Validate input purity
        self._validate_purity(column, "input")
        input_column = column.meta.root_names()[0]

        # Validate arguments
        self.validate_args(**kwargs)

        # Execute plugin
        try:
            result = self.execute(column, **kwargs)
        except Exception as e:
            raise PluginExecutionError(
                f"Plugin '{self.name}' execution failed: {e}",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
                column=input_column,
                original_error=e,
            ) from e

        # Type check output
        if not isinstance(result, pl.Expr):
            raise PluginExecutionError(
                f"Plugin '{self.name}' must return pl.Expr, "
                f"got {type(result).__name__}",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
                column=input_column,
            )

        # Validate output purity
        self._validate_purity(result, "output")
        output_column = result.meta.root_names()[0]

        # Ensure input and output reference the same column
        if input_column != output_column:
            raise PluginExecutionError(
                f"Plugin '{self.name}' violated purity constraint: "
                f"input references '{input_column}' but output references "
                f"'{output_column}'. Column plugins must preserve the column reference.",
                plugin_name=self.name,
                plugin_type=self.__class__.__name__,
                column=input_column,
            )

        return result


class ColumnParser(ColumnPlugin):
    """Base class for column parsers (transformations).

    Column parsers transform column values while maintaining the column structure.
    Common examples: trim whitespace, convert case, parse dates, clean strings.

    Parsers are executed before type coercion and checks in the validation pipeline.

    Example:
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
        ...         pass  # No args to validate
    """

    pass


class ColumnCheck(ColumnPlugin):
    """Base class for column checks (validations).

    Column checks validate column values and return a boolean expression
    indicating which rows pass validation.

    Checks are executed after parsing and type coercion in the validation pipeline.

    Example:
        >>> from nyctea.plugins.base import PluginMetadata
        >>> import polars as pl
        >>>
        >>> class PositiveCheck(ColumnCheck):
        ...     def __init__(self):
        ...         super().__init__(PluginMetadata(name="positive"))
        ...
        ...     def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        ...         return column > 0
        ...
        ...     def validate_args(self, **kwargs) -> None:
        ...         pass  # No args to validate
    """

    pass
