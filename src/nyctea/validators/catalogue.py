"""Validators declared by decorator, and the argument spec taken from their signature.

A decorated function is declared here rather than registered immediately, because
built-ins have no registry at import time. `register_builtins()` turns the catalogue
into registrations.

The argument spec is the function's own signature. Keyword-only parameters are the
contract, so `inspect.Signature.bind` reports a missing or unexpected argument without
running anything. That is what lets a schema's arguments be checked before any data is
read, which #25 needs.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

__all__ = ["CATALOGUE", "Declared", "argument_signature", "bind_arguments"]

Kind = Literal["column_check", "column_parser", "frame_check", "frame_parser"]


def argument_signature(func: Callable[..., Any]) -> inspect.Signature:
    """The signature of everything after the input, which is the argument contract.

    Args:
        func: The decorated function. Its first parameter is the column or frame.

    Returns:
        A signature over the remaining parameters.
    """
    params = list(inspect.signature(func).parameters.values())
    return inspect.Signature(params[1:])


def bind_arguments(name: str, signature: inspect.Signature, kwargs: dict[str, Any]) -> None:
    """Check that `kwargs` satisfies the declared argument signature.

    Args:
        name: Validator name, for the error message.
        signature: The argument signature, from `argument_signature`.
        kwargs: Arguments a schema supplied.

    Raises:
        ValueError: If an argument is missing, unexpected, or otherwise does not bind.
    """
    try:
        signature.bind(**kwargs)
    except TypeError as e:
        expected = str(signature) or "()"
        raise ValueError(f"Validator '{name}' takes {expected}, but got {kwargs}: {e}") from e


@dataclass(frozen=True)
class Declared:
    """One decorated validator, before it is registered into anything."""

    kind: Kind
    name: str
    func: Callable[..., Any]
    description: str = ""
    version: str = "1.0.0"
    tags: tuple[str, ...] = ()
    author: str = ""
    preserve_columns: bool = True
    """Frame validators only: the output must keep the input's columns."""
    preserve_rows: bool = False
    """Frame validators only: the output must keep the input's row count."""

    @property
    def signature(self) -> inspect.Signature:
        """The argument contract this validator's signature declares."""
        return argument_signature(self.func)


CATALOGUE: list[Declared] = []
"""Every validator declared by decorator without a registry in hand."""
