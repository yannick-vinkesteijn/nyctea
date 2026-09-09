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


def test_negative_threshold_is_rejected():
    """A negative row count would silently invert the engine choice."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        Config.set_streaming_row_threshold(-1)


def test_schema_setting_still_wins():
    """Kept as a fallback for one release, so an existing schema keeps working."""
    Config.set_lazy(True)
    with pytest.warns(DeprecationWarning, match="set them on `nyctea.Config`"):
        schema = SchemaModel.from_dict({"lazy": False, "columns": {"a": {"dtype": "Int64"}}})
    assert schema.resolved_lazy is False


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
