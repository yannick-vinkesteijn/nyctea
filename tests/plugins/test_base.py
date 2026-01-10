"""Tests for plugin base classes."""

import pytest

from nyctea.plugins.base import BasePlugin, PluginMetadata


def test_plugin_metadata_creation():
    """Test PluginMetadata creation with all fields."""
    metadata = PluginMetadata(
        name="test_plugin",
        description="A test plugin",
        version="1.0.0",
        tags=["test", "demo"],
        author="Test Author"
    )
    assert metadata.name == "test_plugin"
    assert metadata.description == "A test plugin"
    assert metadata.version == "1.0.0"
    assert list(metadata.tags) == ["test", "demo"]
    assert metadata.author == "Test Author"


def test_plugin_metadata_defaults():
    """Test PluginMetadata default values."""
    metadata = PluginMetadata(name="simple")
    assert metadata.name == "simple"
    assert metadata.description == ""
    assert metadata.version == "1.0.0"
    assert list(metadata.tags) == []
    assert metadata.author == ""


def test_plugin_metadata_immutable():
    """Test that PluginMetadata is immutable (frozen dataclass)."""
    metadata = PluginMetadata(name="test")
    with pytest.raises(AttributeError):
        metadata.name = "changed"  # type: ignore


def test_plugin_metadata_validates_name():
    """Test that PluginMetadata validates name."""
    # Empty name should fail
    with pytest.raises(ValueError, match="cannot be empty"):
        PluginMetadata(name="")

    # Invalid characters should fail
    with pytest.raises(ValueError, match="must be alphanumeric"):
        PluginMetadata(name="invalid name!")


def test_plugin_metadata_allows_underscores_hyphens():
    """Test that underscores and hyphens are allowed in names."""
    metadata1 = PluginMetadata(name="my_plugin")
    assert metadata1.name == "my_plugin"

    metadata2 = PluginMetadata(name="my-plugin")
    assert metadata2.name == "my-plugin"

    metadata3 = PluginMetadata(name="my_plugin-v2")
    assert metadata3.name == "my_plugin-v2"


def test_base_plugin_abstract():
    """Test that BasePlugin cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BasePlugin(PluginMetadata(name="test"))  # type: ignore


def test_base_plugin_has_name_property():
    """Test that BasePlugin subclass has name property."""
    class TestPlugin(BasePlugin):
        def execute(self, input_data, **kwargs):
            return input_data

        def validate_args(self, **kwargs):
            pass

    plugin = TestPlugin(PluginMetadata(name="test_plugin"))
    assert plugin.name == "test_plugin"


def test_base_plugin_repr():
    """Test BasePlugin repr shows name and version."""
    class TestPlugin(BasePlugin):
        def execute(self, input_data, **kwargs):
            return input_data

        def validate_args(self, **kwargs):
            pass

    plugin = TestPlugin(PluginMetadata(name="test", version="2.0.0"))
    assert "TestPlugin" in repr(plugin)
    assert "test" in repr(plugin)
    assert "2.0.0" in repr(plugin)
