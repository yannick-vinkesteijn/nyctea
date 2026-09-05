"""Every declared built-in reaches a registry.

The old hardcoded list in `register.py` was an unverified manual step: a built-in
could be written, exported and unit-tested while never being registered, and the suite
stayed green. The catalogue removes the list; this pins that it removed the gap too.
"""

import pytest

from nyctea import Registry, register_builtins
from nyctea.validators.catalogue import CATALOGUE


@pytest.fixture
def registry():
    registry = Registry()
    register_builtins(registry)
    return registry


def test_every_declared_builtin_is_registered(registry):
    declared = {(d.kind, d.name) for d in CATALOGUE}
    registered = (
        {("column_check", n) for n in registry.column_checks.list_names()}
        | {("column_parser", n) for n in registry.column_parsers.list_names()}
        | {("frame_check", n) for n in registry.frame_checks.list_names()}
        | {("frame_parser", n) for n in registry.frame_parsers.list_names()}
    )
    assert declared == registered


def test_importing_builtins_fills_the_catalogue():
    """A validator exists only if its module was imported, so pin that it is."""
    import nyctea.validators.builtins  # noqa: F401

    assert {d.name for d in CATALOGUE} >= {
        "between",
        "in_set",
        "min_value",
        "unique",
        "strip",
        "to_int",
        "to_float",
        "lower",
        "upper",
    }


def test_declared_signatures_are_the_arg_spec(registry):
    """A schema's arguments bind against the function signature, before any data."""
    check = registry.column_checks.get("between")
    with pytest.raises(ValueError, match=r"takes \(\*, min: float, max: float\).*missing a required argument"):
        check.validate_args(min=0)
