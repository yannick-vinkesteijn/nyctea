"""`schema.verify(registry)` catches authoring mistakes before any data is read."""

import polars as pl
import pytest

from nyctea import ConfigurationError, Registry, SchemaModel, register_builtins


@pytest.fixture
def registry():
    registry = Registry()
    register_builtins(registry)
    return registry


def _schema(checks):
    return SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64", "checks": checks}}})


def test_verify_passes_a_sound_schema(registry):
    _schema([{"name": "min_value", "args": {"min": 0}}]).verify(registry)


def test_unresolved_check_name_is_rejected(registry):
    with pytest.raises(ConfigurationError, match="check 'posiitve' on column 'a' is not registered"):
        _schema([{"name": "posiitve"}]).verify(registry)


def test_bad_arguments_are_rejected(registry):
    """The argument contract is the check's signature, so this needs no data."""
    with pytest.raises(ConfigurationError, match="missing a required argument: 'max'"):
        _schema([{"name": "between", "args": {"min": 0}}]).verify(registry)


def test_duplicate_check_on_column_rejected(registry):
    checks = [{"name": "min_value", "args": {"min": 0}}, {"name": "min_value", "args": {"min": 1}}]
    with pytest.raises(ConfigurationError, match="declared more than once on column 'a'"):
        _schema(checks).verify(registry)


def test_every_problem_is_reported_at_once(registry):
    """Three typos should take one round trip to fix, not three."""
    schema = _schema([{"name": "nope"}, {"name": "between", "args": {"min": 0}}, {"name": "alsonope"}])
    with pytest.raises(ConfigurationError) as exc:
        schema.verify(registry)
    assert str(exc.value).count("\n  ") == 3


def test_validate_verifies_before_reading_data(registry):
    """The mandatory call is the load-bearing half: a method nobody must call proves nothing."""
    schema = _schema([{"name": "posiitve"}])
    with pytest.raises(ConfigurationError, match="is not registered"):
        schema.validate(pl.DataFrame({"a": [1, 2, 3]}), registry)
