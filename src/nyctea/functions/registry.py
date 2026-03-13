"""Strict registries and wrappers for column and frame functions.

This module provides the `FunctionRegistry` class for registering custom parsers
and validation checks. Functions are validated at registration time to ensure
they have correct signatures and behavior.

## Function Types

Nyctea supports four types of registered functions:

### Column Parsers

Transform individual column values (e.g., string manipulation, date parsing).
Must accept a `pl.Expr` and return a `pl.Expr`.

```python
@registry.column_parser(name="to_uppercase")
def uppercase(col: pl.Expr) -> pl.Expr:
    return col.str.to_uppercase()
```

### Column Checks

Validate individual column values. Must accept a `pl.Expr` and return a boolean `pl.Expr`.

```python
@registry.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    return col.gt(0)
```

### Frame Parsers

Transform entire DataFrames. Must accept a `pl.LazyFrame` and return a `pl.LazyFrame`.
Row count must be preserved.

```python
@registry.frame_parser(name="sort_by_date")
def sort_by_date(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.sort("date")
```

### Frame Checks

Validate entire DataFrames. Must accept a `pl.LazyFrame` and return a `pl.LazyFrame`.
Row count must be preserved.

```python
@registry.frame_check(name="min_rows")
def min_rows(lf: pl.LazyFrame, count: int) -> pl.LazyFrame:
    if lf.collect().height < count:
        raise ValueError(f"Frame has fewer than {count} rows")
    return lf
```

## Validation Rules

The registry enforces strict validation rules:

- **Type safety** - All parameters and returns must be type-annotated
- **Column purity** - Column functions can only reference their input column
- **Frame shape** - Frame functions must preserve columns and row count
- **JSON-serializable defaults** - Default parameter values must be JSON-serializable
- **No variadic args** - Functions cannot use `*args` or `**kwargs`

## Key Classes

- `FunctionRegistry` - Main registry for all function types
- `ColumnFunctionWrapper` - Wrapper that enforces column purity
- `FrameFunctionWrapper` - Wrapper that enforces frame shape constraints
- `SignatureValidator` - Validates function signatures at registration time

## Exceptions

- `RegistryError` - Base exception for registration failures
- `ColumnPurityError` - Raised when column functions violate purity rules
- `FrameShapeError` - Raised when frame functions alter shape unexpectedly

## Example

```python
from nyctea.functions import FunctionRegistry
import polars as pl

registry = FunctionRegistry()


# Register a column parser
@registry.column_parser(name="trim")
def trim_whitespace(col: pl.Expr) -> pl.Expr:
    return col.str.strip_chars()


# Register a column check with parameters
@registry.column_check(name="in_range")
def in_range(col: pl.Expr, min_val: float, max_val: float) -> pl.Expr:
    return col.is_between(min_val, max_val)


# Register a frame parser
@registry.frame_parser(name="dedupe")
def deduplicate(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.unique()


# Use in validation
from nyctea import validate, SchemaModel

schema = SchemaModel.from_dict(
    {
        "columns": {
            "age": {
                "dtype": "Int64",
                "parsers": [{"name": "trim"}],
                "checks": [{"name": "in_range", "args": {"min_val": 0, "max_val": 120}}],
            }
        },
        "frame_parsers": [{"name": "dedupe"}],
    }
)

result = validate(df, schema, registry)
```
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from functools import update_wrapper
from typing import Annotated, Any, Generic, TypeVar, get_args, get_origin, get_type_hints

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

ColumnFunction = Callable[..., pl.Expr]
FrameFunction = Callable[..., pl.LazyFrame]
FrameParserFunction = FrameFunction
FrameCheckFunction = FrameFunction

InFunc = TypeVar("InFunc", bound=Callable[..., Any])
OutFunc = TypeVar("OutFunc", bound=Callable[..., Any])


class RegistryError(ValueError):
    """Raised when a function cannot be registered."""


class ColumnPurityError(RegistryError):
    """Raised when a column function touches disallowed columns."""


class FrameShapeError(RegistryError):
    """Raised when a frame function alters shape unexpectedly."""


class SignatureValidator:
    """Utility class to enforce function signatures at registration time."""

    @staticmethod
    def _strip_annotated(annotation: Any) -> Any:
        origin = get_origin(annotation)
        if origin is Annotated:
            args = get_args(annotation)
            if args:
                return args[0]
        return annotation

    @staticmethod
    def validate(
        func: Callable[..., Any],
        *,
        expected_first: type,
        expected_return: type,
        kind: str,
    ) -> None:
        """Validate callable signature and return type.

        Args:
            func: Function to validate.
            expected_first: Expected annotation for the first argument.
            expected_return: Expected return annotation.
            kind: Human-readable function kind for error messages.

        Raises:
            RegistryError: If any signature constraint is violated.
        """
        if not callable(func):
            raise RegistryError(f"{kind} must be callable")

        signature = inspect.signature(func)
        try:
            hints = get_type_hints(func, globalns=getattr(func, "__globals__", {}), localns=None)
        except Exception as err:
            raise RegistryError(
                f"{kind} '{func.__name__}' annotations could not be resolved; "
                "ensure all annotations are valid types (not unresolved forward references)"
            ) from err

        parameters = list(signature.parameters.values())
        if not parameters:
            raise RegistryError(f"{kind} '{func.__name__}' must accept at least one argument")

        first = parameters[0]
        if first.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            raise RegistryError(
                f"{kind} '{func.__name__}' must declare the first parameter as positional "
                f"and annotated as {expected_first.__name__}"
            )

        first_hint = hints.get(first.name)
        if first_hint is None:
            raise RegistryError(
                f"{kind} '{func.__name__}' must annotate the first parameter as {expected_first.__name__}"
            )
        first_hint = SignatureValidator._strip_annotated(first_hint)
        if first_hint is not expected_first:
            raise RegistryError(
                f"{kind} '{func.__name__}' must annotate the first parameter as {expected_first.__name__}"
            )

        return_hint = hints.get("return")
        if return_hint is None:
            raise RegistryError(f"{kind} '{func.__name__}' must return {expected_return.__name__}")
        return_hint = SignatureValidator._strip_annotated(return_hint)
        if return_hint is not expected_return:
            raise RegistryError(f"{kind} '{func.__name__}' must return {expected_return.__name__}")

        for param in parameters[1:]:
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                raise RegistryError(
                    f"{kind} '{func.__name__}' may not use *args or **kwargs to avoid silent argument handling"
                )
            param_hint = hints.get(param.name)
            if param_hint is not None:
                param_hint = SignatureValidator._strip_annotated(param_hint)
            if param_hint is expected_first:
                raise RegistryError(
                    f"{kind} '{func.__name__}' may not accept multiple {expected_first.__name__} parameters"
                )
            if param.default is inspect._empty:
                continue
            try:
                json.dumps(param.default)  # type: ignore[arg-type]
            except TypeError as err:
                raise RegistryError(
                    f"{kind} '{func.__name__}' default for parameter '{param.name}' must be JSON-serializable"
                ) from err


class ColumnFunctionWrapper:
    """Callable wrapper that enforces column purity at invocation time."""

    def __init__(self, func: ColumnFunction, *, kind: str) -> None:
        self.func = func
        self.kind = kind
        update_wrapper(self, func)

    def __call__(self, column: pl.Expr, *args: Any, **kwargs: Any) -> pl.Expr:
        """Invoke the wrapped function and enforce purity.

        Args:
            column: Source column expression.
            *args: Positional arguments passed to the wrapped function.
            **kwargs: Keyword arguments passed to the wrapped function.

        Returns:
            pl.Expr: Resulting expression from the wrapped function.

        Raises:
            ColumnPurityError: If the input or output violates purity rules.
            RegistryError: If the wrapped function returns an invalid type.
        """
        if not isinstance(column, pl.Expr):
            raise ColumnPurityError(
                f"{self.kind} '{self.func.__name__}' received non-expression input of type '{type(column).__name__}'"
            )

        source_columns = column.meta.root_names()
        if len(source_columns) != 1:
            raise ColumnPurityError(
                f"{self.kind} '{self.func.__name__}' can only operate on a single column expression"
            )

        result = self.func(column, *args, **kwargs)
        if not isinstance(result, pl.Expr):
            raise RegistryError(
                f"{self.kind} '{self.func.__name__}' must return a pl.Expr, got '{type(result).__name__}'"
            )

        referenced = set(result.meta.root_names())
        allowed = set(source_columns)
        if not referenced:
            raise ColumnPurityError(
                f"{self.kind} '{self.func.__name__}' must reference the source column '{next(iter(allowed))}'"
            )
        if referenced != allowed:
            bad = ", ".join(sorted(referenced - allowed))
            raise ColumnPurityError(
                f"{self.kind} '{self.func.__name__}' referenced disallowed columns: {bad or 'unknown'}"
            )
        return result


class FrameFunctionWrapper:
    """Callable wrapper that enforces frame output type and shape."""

    def __init__(self, func: FrameFunction, *, kind: str, enforce_row_count: bool) -> None:
        self.func = func
        self.kind = kind
        self.enforce_row_count = enforce_row_count
        update_wrapper(self, func)

    def __call__(self, frame: pl.LazyFrame, *args: Any, **kwargs: Any) -> pl.LazyFrame:
        """Invoke the wrapped function and enforce shape constraints.

        Args:
            frame: Input lazy frame.
            *args: Positional arguments passed to the wrapped function.
            **kwargs: Keyword arguments passed to the wrapped function.

        Returns:
            pl.LazyFrame: Output frame from the wrapped function.

        Raises:
            FrameShapeError: If type, column set, or row count are altered.
        """
        if not isinstance(frame, pl.LazyFrame):
            raise FrameShapeError(
                f"{self.kind} '{self.func.__name__}' received non-lazy input of type '{type(frame).__name__}'"
            )

        input_columns = tuple(frame.collect_schema().names())
        input_rows = self._row_count(frame) if self.enforce_row_count else None
        result = self.func(frame, *args, **kwargs)
        if not isinstance(result, pl.LazyFrame):
            raise FrameShapeError(
                f"{self.kind} '{self.func.__name__}' must return a pl.LazyFrame, got '{type(result).__name__}'"
            )

        output_columns = tuple(result.collect_schema().names())
        if input_columns != output_columns:
            raise FrameShapeError(
                f"{self.kind} '{self.func.__name__}' must preserve columns. "
                f"Before: {input_columns} After: {output_columns}"
            )

        if self.enforce_row_count:
            output_rows = self._row_count(result)
            if input_rows != output_rows:
                raise FrameShapeError(
                    f"{self.kind} '{self.func.__name__}' must preserve row count. "
                    f"Before: {input_rows} After: {output_rows}"
                )

        return result

    @staticmethod
    def _row_count(frame: pl.LazyFrame) -> int:
        """Collect row count for a lazy frame."""
        count_df = frame.select(pl.len().alias("row_count")).collect()
        return int(count_df.to_series(0).item())


class DecoratorAdapter(Generic[InFunc, OutFunc]):
    """Decorator-like helper that avoids nested functions."""

    def __init__(
        self,
        registrar: Callable[[InFunc, str | None], OutFunc],
        name: str | None = None,
    ) -> None:
        self._registrar = registrar
        self._name = name

    def __call__(
        self,
        func: InFunc | None = None,
        *,
        name: str | None = None,
    ) -> OutFunc | DecoratorAdapter[InFunc, OutFunc]:
        """Apply registration or return a configured adapter."""
        chosen = name or self._name
        if func is None:
            return DecoratorAdapter(self._registrar, chosen)
        return self._registrar(func, name=chosen)


class FunctionRegistry(BaseModel):
    """Holds all registered functions with strict validation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    column_parsers: dict[str, ColumnFunctionWrapper] = Field(default_factory=dict)
    column_checks: dict[str, ColumnFunctionWrapper] = Field(default_factory=dict)
    frame_parsers: dict[str, FrameFunctionWrapper] = Field(default_factory=dict)
    frame_checks: dict[str, FrameFunctionWrapper] = Field(default_factory=dict)

    @property
    def column_parser(self) -> DecoratorAdapter[ColumnFunction, ColumnFunctionWrapper]:
        """Decorator for registering column parsers."""
        return DecoratorAdapter(self.register_column_parser)

    @property
    def column_check(self) -> DecoratorAdapter[ColumnFunction, ColumnFunctionWrapper]:
        """Decorator for registering column checks."""
        return DecoratorAdapter(self.register_column_check)

    @property
    def frame_parser(self) -> DecoratorAdapter[FrameParserFunction, FrameFunctionWrapper]:
        """Decorator for registering frame parsers."""
        return DecoratorAdapter(self.register_frame_parser)

    @property
    def frame_check(self) -> DecoratorAdapter[FrameCheckFunction, FrameFunctionWrapper]:
        """Decorator for registering frame checks."""
        return DecoratorAdapter(self.register_frame_check)

    def register_column_parser(
        self,
        func: ColumnFunction,
        *,
        name: str | None = None,
    ) -> ColumnFunctionWrapper:
        """Register a column parser."""
        return self._register_column(func, name=name, store=self.column_parsers, kind="column parser")

    def register_column_check(
        self,
        func: ColumnFunction,
        *,
        name: str | None = None,
    ) -> ColumnFunctionWrapper:
        """Register a column check."""
        return self._register_column(func, name=name, store=self.column_checks, kind="column check")

    def register_frame_parser(
        self,
        func: FrameParserFunction,
        *,
        name: str | None = None,
    ) -> FrameFunctionWrapper:
        """Register a frame parser."""
        return self._register_frame(
            func,
            name=name,
            store=self.frame_parsers,
            kind="frame parser",
            enforce_rows=True,
        )

    def register_frame_check(
        self,
        func: FrameCheckFunction,
        *,
        name: str | None = None,
    ) -> FrameFunctionWrapper:
        """Register a frame check."""
        return self._register_frame(
            func,
            name=name,
            store=self.frame_checks,
            kind="frame check",
            enforce_rows=True,
        )

    def _register_column(
        self,
        func: ColumnFunction,
        *,
        name: str | None,
        store: dict[str, ColumnFunctionWrapper],
        kind: str,
    ) -> ColumnFunctionWrapper:
        """Register a column-level function after validation."""
        SignatureValidator.validate(
            func,
            expected_first=pl.Expr,
            expected_return=pl.Expr,
            kind=kind,
        )
        wrapped = ColumnFunctionWrapper(func, kind=kind)
        self._insert(name=name, func=wrapped, store=store, kind=kind)
        return wrapped

    def _register_frame(
        self,
        func: F,
        *,
        name: str | None,
        store: dict[str, FrameFunctionWrapper],
        kind: str,
        enforce_rows: bool,
    ) -> FrameFunctionWrapper:
        """Register a frame-level function after validation."""
        SignatureValidator.validate(
            func,
            expected_first=pl.LazyFrame,
            expected_return=pl.LazyFrame,
            kind=kind,
        )
        wrapped = FrameFunctionWrapper(func, kind=kind, enforce_row_count=enforce_rows)
        self._insert(name=name, func=wrapped, store=store, kind=kind)
        return wrapped

    def _insert(self, *, name: str | None, func: F, store: dict[str, F], kind: str) -> None:
        """Insert a validated function into its registry."""
        func_name = name or getattr(func, "__name__", "")
        if not func_name:
            raise RegistryError(f"{kind} functions must have a name")
        if func_name in store:
            raise RegistryError(f"{kind} '{func_name}' is already registered")
        store[func_name] = func


__all__ = [
    "ColumnFunctionWrapper",
    "ColumnPurityError",
    "DecoratorAdapter",
    "FrameFunctionWrapper",
    "FrameShapeError",
    "FunctionRegistry",
    "RegistryError",
]
