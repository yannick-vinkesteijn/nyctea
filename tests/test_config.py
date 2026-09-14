"""`nyctea.Config` holds settings that describe the run, not the data."""

import polars as pl
import pytest

from nyctea import Config, Registry, SchemaModel, register_builtins


@pytest.fixture(autouse=True)
def _restore():
    saved = Config.save()
    yield
    Config.load(saved)


def test_setters_change_the_global_value():
    Config.set_streaming_row_threshold(0)
    assert Config.streaming_row_threshold() == 0


def test_context_manager_scopes_a_setting():
    Config.set_streaming_row_threshold(10)
    with Config(streaming_row_threshold=500):
        assert Config.streaming_row_threshold() == 500
    assert Config.streaming_row_threshold() == 10


def test_decorator_scopes_a_setting():
    @Config(lazy=False)
    def inside():
        return Config.lazy()

    assert inside() is False
    assert Config.lazy() is True


def test_unknown_setting_is_rejected():
    """A typo in a scoped setting is a mistake, not a silently ignored key."""
    with pytest.raises(ValueError, match="Unknown nyctea setting 'nope'"), Config(nope=1):
        pass


def test_invalid_context_preserves_state():
    Config.set_lazy(True)

    with pytest.raises(ValueError, match="Unknown nyctea setting 'nope'"), Config(lazy=False, nope=1):
        pass

    assert Config.lazy() is True


def test_restore_defaults_resets_shipped_values():
    Config.set_streaming_row_threshold(0)
    Config.set_lazy(False)

    Config.restore_defaults()

    assert Config.streaming_row_threshold() != 0
    assert Config.lazy() is True


def test_negative_threshold_is_rejected():
    """A negative row count would silently invert the engine choice."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        Config.set_streaming_row_threshold(-1)


def test_schema_rejects_run_settings():
    """A schema declaring a moved setting is told where the setting went.

    `extra="forbid"` alone would reject it with pydantic's generic "extra inputs are
    not permitted", which does not tell someone upgrading from an earlier pre-release
    what to do. The error names `nyctea.Config` instead.
    """
    for field in ("lazy", "streaming_row_threshold"):
        with pytest.raises(ValueError, match=f"`{field}` moved from the schema to `nyctea.Config`"):
            SchemaModel.from_dict({field: False, "columns": {"a": {"dtype": "Int64"}}})


def test_unknown_schema_field_still_rejected():
    """The migration message does not swallow ordinary typos."""
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        SchemaModel.from_dict({"lzy": False, "columns": {"a": {"dtype": "Int64"}}})


def test_config_applies_when_schema_is_silent():
    schema = SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64"}}})
    with Config(lazy=False):
        assert schema.resolved_lazy is False


def test_config_reaches_a_validation_run():
    registry = Registry()
    register_builtins(registry)
    schema = SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64", "nullable": True}}})
    with Config(lazy=False):
        result = schema.validate(pl.DataFrame({"a": [1, 2]}), registry)
    assert isinstance(result.data, pl.DataFrame)


def test_repr_names_no_run_settings():
    """`__repr__` interpolated `lazy=` until the field moved to `nyctea.Config`.

    Nothing else would catch the name creeping back into that f-string, because a
    repr is not asserted anywhere else in the suite.
    """
    schema = SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64"}}})

    text = repr(schema)

    assert text == "<SchemaModel coerce=True, on_failure='raise', columns=[a]>"
    for moved in ("lazy", "streaming_row_threshold"):
        assert moved not in text
