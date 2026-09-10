"""Decorators for declaring validators as plain functions.

Write an expression and decorate it. The class hierarchy still runs underneath,
because `ColumnValidator.__call__` is what proves a check or parser only touches its
own column, but nothing about it reaches the author of a validator.

Without a registry the decorated function is declared into `CATALOGUE`, which is what
built-ins do, since they have no registry at import time. With `registry=` it is
registered immediately, which is what user code with a registry in hand should do.

Each decorator works bare (`@checker`) or parameterized (`@checker(name=...)`). Bare
form infers the validator's name from the function. Two `@overload`s per decorator
give each call shape its own return type, rather than the union-typed single
signature #42 found unusable under a real type checker.
"""

from collections.abc import Callable, Sequence
from typing import Any, TypeVar, overload

import polars as pl

from nyctea.validators.base import ValidatorMetadata
from nyctea.validators.catalogue import CATALOGUE, Declared, Kind, bind_arguments
from nyctea.validators.column import ColumnCheck, ColumnParser
from nyctea.validators.frame import FrameCheck, FrameParser
from nyctea.validators.registry import Registry

__all__ = ["build_validator", "checker", "frame_checker", "frame_parser", "parser"]

# TypeVars, not plain aliases: binding to the concrete decorated function at each
# call site is what actually preserves its signature through the bare form, rather
# than erasing every parameter to `...`.
_ColumnFn = TypeVar("_ColumnFn", bound=Callable[..., pl.Expr])
_FrameFn = TypeVar("_FrameFn", bound=Callable[..., pl.LazyFrame])

_BASES: dict[Kind, type[Any]] = {
    "column_check": ColumnCheck,
    "column_parser": ColumnParser,
    "frame_check": FrameCheck,
    "frame_parser": FrameParser,
}

_REGISTER = {
    "column_check": "register_column_check",
    "column_parser": "register_column_parser",
    "frame_check": "register_frame_check",
    "frame_parser": "register_frame_parser",
}


def build_validator(declared: Declared) -> Any:
    """Wrap a declared function in the validator class its kind requires.

    One factory for all four kinds, rather than an anonymous class per decorator. The
    base class keeps its own `__init__`, so this only supplies the two abstract methods.

    Args:
        declared: The decorated function and its metadata.

    Returns:
        A validator instance ready to register.
    """
    base = _BASES[declared.kind]
    signature = declared.signature
    metadata = ValidatorMetadata(
        name=declared.name,
        description=declared.description or declared.func.__doc__ or "",
        version=declared.version,
        tags=list(declared.tags),
        author=declared.author,
    )
    first = "column" if declared.kind.startswith("column") else "frame"
    cls = type(
        f"Declared{base.__name__}",
        (base,),
        {
            "execute": _execute_method(declared.func, first),
            "validate_args": lambda _self, **kwargs: bind_arguments(declared.name, signature, kwargs),
        },
    )
    if declared.kind == "frame_parser":
        # Only a frame parser transforms, so only it can be asked to preserve shape.
        return cls(
            metadata,
            preserve_columns=declared.preserve_columns,
            preserve_rows=declared.preserve_rows,
        )
    return cls(metadata)


def _execute_method(func: Callable[..., Any], first: str) -> Callable[..., Any]:
    """Build an `execute` whose first parameter is named as the base class requires."""
    if first == "column":

        def execute(self, column: pl.Expr, **kwargs: Any) -> pl.Expr:  # noqa: ANN001, ARG001
            return func(column, **kwargs)

    else:

        def execute(self, frame: pl.LazyFrame, **kwargs: Any) -> pl.LazyFrame:  # noqa: ANN001, ARG001
            return func(frame, **kwargs)

    return execute


def _dispatch(
    kind: Kind,
    func: Callable[..., Any] | None,
    *,
    name: str | None,
    description: str,
    version: str,
    tags: Sequence[str] | None,
    author: str,
    registry: Registry | None,
    preserve_columns: bool = True,
    preserve_rows: bool = False,
) -> Any:
    """Shared runtime behind every declaration decorator.

    `func` is the decorated function for the bare form (`@checker`) and `None` for
    the parameterized form (`@checker(...)`), which is what selects between
    returning the function immediately or returning a decorator for it.

    Args:
        kind: Validator kind, selects the base class and the registry method.
        func: The decorated function, bare form only.
        name: Validator name. Bare form infers it from `func.__name__`.
        description: Human-readable description. Defaults to the function's docstring.
        version: Validator version.
        tags: Optional tags for discovery.
        author: Validator author.
        registry: Register immediately into this registry. Without it the validator
            is declared into `CATALOGUE` and registered by `register_builtins`.
        preserve_columns: Frame parsers only. Output must keep the input's columns.
        preserve_rows: Frame parsers only. Output must keep the input's row count.

    Returns:
        The function unchanged (bare form), or a decorator that returns it unchanged
        (parameterized form).
    """

    def wrap(target: Callable[..., Any]) -> Callable[..., Any]:
        declared = Declared(
            kind=kind,
            # Every caller decorates a plain `def`, never an arbitrary callable, so
            # __name__ is always there; Callable[..., Any] just cannot say so.
            name=name or target.__name__,  # ty: ignore[unresolved-attribute]
            func=target,
            description=description,
            version=version,
            tags=tuple(tags or ()),
            author=author,
            preserve_columns=preserve_columns,
            preserve_rows=preserve_rows,
        )
        if registry is None:
            CATALOGUE.append(declared)
        else:
            getattr(registry, _REGISTER[kind])(build_validator(declared))
        return target

    return wrap(func) if func is not None else wrap


@overload
def checker(func: _ColumnFn) -> _ColumnFn: ...
@overload
def checker(
    func: None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
) -> Callable[[_ColumnFn], _ColumnFn]: ...
def checker(
    func: _ColumnFn | None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
) -> Any:
    """Declare a function as a column check.

    Works bare (`@checker`), which infers the check's name from the function, or
    parameterized (`@checker(...)`) for an explicit name or the rest of the
    contract. Arguments after `name` are keyword-only and are checked against a
    schema's arguments before any data is read.

    Args:
        func: The decorated function. Only present for the bare form; leave it out
            and call with keyword arguments for the parameterized form.
        name: Check name. Bare form infers it from the function's `__name__`.
        description: Human-readable description. Defaults to the function's docstring.
        version: Validator version.
        tags: Optional tags for discovery.
        author: Validator author.
        registry: Register immediately into this registry. Without it the check is
            declared into `CATALOGUE` and registered by `register_builtins`.

    Returns:
        The function unchanged (bare form), or a decorator that returns it unchanged
        (parameterized form).
    """
    return _dispatch(
        "column_check",
        func,
        name=name,
        description=description,
        version=version,
        tags=tags,
        author=author,
        registry=registry,
    )


@overload
def parser(func: _ColumnFn) -> _ColumnFn: ...
@overload
def parser(
    func: None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
) -> Callable[[_ColumnFn], _ColumnFn]: ...
def parser(
    func: _ColumnFn | None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
) -> Any:
    """Declare a function as a column parser.

    Works bare (`@parser`), which infers the parser's name from the function, or
    parameterized (`@parser(...)`) for an explicit name or the rest of the contract.
    Arguments after `name` are keyword-only and are checked against a schema's
    arguments before any data is read.

    Args:
        func: The decorated function. Only present for the bare form; leave it out
            and call with keyword arguments for the parameterized form.
        name: Parser name. Bare form infers it from the function's `__name__`.
        description: Human-readable description. Defaults to the function's docstring.
        version: Validator version.
        tags: Optional tags for discovery.
        author: Validator author.
        registry: Register immediately into this registry. Without it the parser is
            declared into `CATALOGUE` and registered by `register_builtins`.

    Returns:
        The function unchanged (bare form), or a decorator that returns it unchanged
        (parameterized form).
    """
    return _dispatch(
        "column_parser",
        func,
        name=name,
        description=description,
        version=version,
        tags=tags,
        author=author,
        registry=registry,
    )


@overload
def frame_checker(func: _FrameFn) -> _FrameFn: ...
@overload
def frame_checker(
    func: None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
) -> Callable[[_FrameFn], _FrameFn]: ...
def frame_checker(
    func: _FrameFn | None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
) -> Any:
    """Declare a function as a frame check.

    Works bare (`@frame_checker`), which infers the check's name from the function,
    or parameterized (`@frame_checker(...)`) for an explicit name or the rest of the
    contract. Arguments after `name` are keyword-only and are checked against a
    schema's arguments before any data is read.

    Args:
        func: The decorated function. Only present for the bare form; leave it out
            and call with keyword arguments for the parameterized form.
        name: Check name. Bare form infers it from the function's `__name__`.
        description: Human-readable description. Defaults to the function's docstring.
        version: Validator version.
        tags: Optional tags for discovery.
        author: Validator author.
        registry: Register immediately into this registry. Without it the check is
            declared into `CATALOGUE` and registered by `register_builtins`.

    Returns:
        The function unchanged (bare form), or a decorator that returns it unchanged
        (parameterized form).
    """
    return _dispatch(
        "frame_check",
        func,
        name=name,
        description=description,
        version=version,
        tags=tags,
        author=author,
        registry=registry,
    )


@overload
def frame_parser(func: _FrameFn) -> _FrameFn: ...
@overload
def frame_parser(
    func: None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
    preserve_columns: bool = True,
    preserve_rows: bool = False,
) -> Callable[[_FrameFn], _FrameFn]: ...
def frame_parser(
    func: _FrameFn | None = None,
    *,
    name: str | None = None,
    description: str = "",
    version: str = "1.0.0",
    tags: Sequence[str] | None = None,
    author: str = "",
    registry: Registry | None = None,
    preserve_columns: bool = True,
    preserve_rows: bool = False,
) -> Any:
    """Declare a function as a frame parser.

    Works bare (`@frame_parser`), which infers the parser's name from the function,
    or parameterized (`@frame_parser(...)`) for an explicit name or the rest of the
    contract. Arguments after `name` are keyword-only and are checked against a
    schema's arguments before any data is read.

    Args:
        func: The decorated function. Only present for the bare form; leave it out
            and call with keyword arguments for the parameterized form.
        name: Parser name. Bare form infers it from the function's `__name__`.
        description: Human-readable description. Defaults to the function's docstring.
        version: Validator version.
        tags: Optional tags for discovery.
        author: Validator author.
        registry: Register immediately into this registry. Without it the parser is
            declared into `CATALOGUE` and registered by `register_builtins`.
        preserve_columns: Output must keep the input's columns.
        preserve_rows: Output must keep the input's row count.

    Returns:
        The function unchanged (bare form), or a decorator that returns it unchanged
        (parameterized form).
    """
    return _dispatch(
        "frame_parser",
        func,
        name=name,
        description=description,
        version=version,
        tags=tags,
        author=author,
        registry=registry,
        preserve_columns=preserve_columns,
        preserve_rows=preserve_rows,
    )
