"""Tests for plugin registry."""

import pytest

from nyctea.exceptions import RegistrationError
from nyctea.plugins.base import ValidatorMetadata
from nyctea.plugins.column import ColumnParser
from nyctea.plugins.registry import Registry, PluginRegistry


class TestParser(ColumnParser):
    """Test parser."""

    def __init__(self, name="test"):
        super().__init__(ValidatorMetadata(name=name, tags=["test"]))

    def execute(self, column, **kwargs):
        return column

    def validate_args(self, **kwargs):
        pass


def test_plugin_registry_creation():
    """Test creating a plugin registry."""
    registry = PluginRegistry(ColumnParser)
    assert registry.plugin_type == ColumnParser
    assert len(registry) == 0


def test_plugin_registry_register():
    """Test registering a plugin."""
    registry = PluginRegistry(ColumnParser)
    plugin = TestParser()

    registry.register(plugin)
    assert len(registry) == 1
    assert registry.has("test")


def test_plugin_registry_get():
    """Test getting a plugin by name."""
    registry = PluginRegistry(ColumnParser)
    plugin = TestParser()
    registry.register(plugin)

    retrieved = registry.get("test")
    assert retrieved is plugin


def test_plugin_registry_get_nonexistent():
    """Test getting a nonexistent plugin raises KeyError."""
    registry = PluginRegistry(ColumnParser)

    with pytest.raises(KeyError, match="No plugin named 'missing'"):
        registry.get("missing")


def test_plugin_registry_collision_detection():
    """Test that duplicate names are rejected."""
    registry = PluginRegistry(ColumnParser)
    plugin1 = TestParser(name="duplicate")
    plugin2 = TestParser(name="duplicate")

    registry.register(plugin1)

    with pytest.raises(RegistrationError, match="already registered"):
        registry.register(plugin2)


def test_plugin_registry_type_validation():
    """Test that wrong plugin types are rejected."""
    from nyctea.plugins.frame import FrameParser
    from nyctea.plugins.base import ValidatorMetadata

    class TestFrameParser(FrameParser):
        def execute(self, frame, **kwargs):
            return frame

        def validate_args(self, **kwargs):
            pass

    registry = PluginRegistry(ColumnParser)
    frame_plugin = TestFrameParser(ValidatorMetadata(name="frame"))

    with pytest.raises(TypeError, match="Registry expects ColumnParser"):
        registry.register(frame_plugin)


def test_plugin_registry_list_names():
    """Test listing plugin names."""
    registry = PluginRegistry(ColumnParser)
    registry.register(TestParser(name="a"))
    registry.register(TestParser(name="c"))
    registry.register(TestParser(name="b"))

    names = registry.list_names()
    assert names == ["a", "b", "c"]  # Should be sorted


def test_plugin_registry_list_all():
    """Test listing all plugins."""
    registry = PluginRegistry(ColumnParser)
    p1 = TestParser(name="one")
    p2 = TestParser(name="two")

    registry.register(p1)
    registry.register(p2)

    all_plugins = registry.list_all()
    assert len(all_plugins) == 2
    assert p1 in all_plugins
    assert p2 in all_plugins


def test_plugin_registry_get_by_tag():
    """Test getting plugins by tag."""
    class TaggedParser(ColumnParser):
        def __init__(self, name, tags):
            super().__init__(ValidatorMetadata(name=name, tags=tags))

        def execute(self, column, **kwargs):
            return column

        def validate_args(self, **kwargs):
            pass

    registry = PluginRegistry(ColumnParser)
    p1 = TaggedParser("p1", ["numeric", "validation"])
    p2 = TaggedParser("p2", ["string"])
    p3 = TaggedParser("p3", ["numeric"])

    registry.register(p1)
    registry.register(p2)
    registry.register(p3)

    numeric_plugins = registry.get_by_tag("numeric")
    assert len(numeric_plugins) == 2
    assert p1 in numeric_plugins
    assert p3 in numeric_plugins

    string_plugins = registry.get_by_tag("string")
    assert len(string_plugins) == 1
    assert p2 in string_plugins


def test_master_registry_creation():
    """Test creating a master registry."""
    registry = Registry()

    assert registry.column_parsers is not None
    assert registry.column_checks is not None
    assert registry.frame_parsers is not None
    assert registry.frame_checks is not None


def test_master_registry_get_counts():
    """Test getting plugin counts."""
    registry = Registry()

    counts = registry.get_plugin_counts()
    assert counts["column_parsers"] == 0
    assert counts["column_checks"] == 0
    assert counts["frame_parsers"] == 0
    assert counts["frame_checks"] == 0

    # Register a parser
    registry.register_column_parser(TestParser())
    counts = registry.get_plugin_counts()
    assert counts["column_parsers"] == 1


def test_master_registry_repr():
    """Test master registry repr."""
    registry = Registry()
    repr_str = repr(registry)

    assert "Registry" in repr_str
    assert "column_parsers" in repr_str
