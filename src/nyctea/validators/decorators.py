"""Decorators for declaring validators as plain functions.

Write an expression and decorate it. The class hierarchy still runs underneath,
because `ColumnValidator.__call__` is what proves a check or parser only touches its
own column, but nothing about it reaches the author of a validator.

Without a registry the decorated function is declared into `CATALOGUE`, which is what
built-ins do, since they have no registry at import time. With `registry=` it is
registered immediately, which is what user code with a registry in hand should do.
"""

from collections.abc import Callable, Sequence
from typing import Any

import polars as pl

from nyctea.validators.base import ValidatorMetadata
from nyctea.validators.catalogue import CATALOGUE, Declared, Kind, bind_arguments
from nyctea.validators.column import ColumnCheck, ColumnParser
from nyctea.validators.frame import FrameCheck, FrameParser
from nyctea.validators.registry import Registry

__all__ = ["build_validator", "checker", "frame_checker", "frame_parser", "parser"]

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


def _declare(kind: Kind) -> Callable[..., Any]:
    """Build the decorator for one validator kind."""

    def decorator(
        name: str,
        description: str = "",
        version: str = "1.0.0",
        tags: Sequence[str] | None = None,
        author: str = "",
        registry: Registry | None = None,
        preserve_columns: bool = True,
        preserve_rows: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def wrap(func: Callable[..., Any]) -> Callable[..., Any]:
            declared = Declared(
                kind=kind,
                name=name,
                func=func,
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
            return func

        return wrap

    decorator.__name__ = kind
    return decorator


checker = _declare("column_check")
parser = _declare("column_parser")
frame_checker = _declare("frame_check")
frame_parser = _declare("frame_parser")

_DOC = """Declare a function as a {what}.

Arguments after the first are the validator's contract. Make them keyword-only and
they are checked against a schema's arguments before any data is read.

Args:
    name: Unique validator name.
    description: Human-readable description. Defaults to the function's docstring.
    version: Validator version.
    tags: Optional tags for discovery.
    author: Validator author.
    registry: Register immediately into this registry. Without it the validator is
        declared into `CATALOGUE` and registered by `register_builtins`.
    preserve_columns: Frame validators only. Output must keep the input's columns.
    preserve_rows: Frame validators only. Output must keep the input's row count.

Returns:
    The decorator, which returns the function unchanged.
"""
for _fn, _what in (
    (checker, "column check"),
    (parser, "column parser"),
    (frame_checker, "frame check"),
    (frame_parser, "frame parser"),
):
    _fn.__doc__ = _DOC.format(what=_what)
