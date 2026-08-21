"""Tests for validator base classes."""

import pytest

from nyctea.validators.base import Validator, ValidatorMetadata


def test_plugin_metadata_creation():
    """Test ValidatorMetadata creation with all fields."""
    metadata = ValidatorMetadata(
        name="test_validator",
        description="A test validator",
        version="1.0.0",
        tags=["test", "demo"],
        author="Test Author",
    )
    assert metadata.name == "test_validator"
    assert metadata.description == "A test validator"
    assert metadata.version == "1.0.0"
    assert list(metadata.tags) == ["test", "demo"]
    assert metadata.author == "Test Author"


def test_plugin_metadata_defaults():
    """Test ValidatorMetadata default values."""
    metadata = ValidatorMetadata(name="simple")
    assert metadata.name == "simple"
    assert metadata.description == ""
    assert metadata.version == "1.0.0"
    assert list(metadata.tags) == []
    assert metadata.author == ""


def test_plugin_metadata_immutable():
    """Test that ValidatorMetadata is immutable (frozen dataclass)."""
    metadata = ValidatorMetadata(name="test")
    with pytest.raises(AttributeError):
        metadata.name = "changed"  # type: ignore[misc]


def test_plugin_metadata_validates_name():
    """Test that ValidatorMetadata validates name."""
    # Empty name should fail
    with pytest.raises(ValueError, match="cannot be empty"):
        ValidatorMetadata(name="")

    # Invalid characters should fail
    with pytest.raises(ValueError, match="must be alphanumeric"):
        ValidatorMetadata(name="invalid name!")


def test_plugin_metadata_allows_underscores_hyphens():
    """Test that underscores and hyphens are allowed in names."""
    metadata1 = ValidatorMetadata(name="my_plugin")
    assert metadata1.name == "my_plugin"

    metadata2 = ValidatorMetadata(name="my-validator")
    assert metadata2.name == "my-validator"

    metadata3 = ValidatorMetadata(name="my_plugin-v2")
    assert metadata3.name == "my_plugin-v2"


def test_base_plugin_abstract():
    """Test that Validator cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        Validator(ValidatorMetadata(name="test"))  # type: ignore[abstract]


def test_base_plugin_has_name_property():
    """Test that Validator subclass has name property."""

    class TestValidator(Validator):
        def execute(self, input_data, **kwargs):
            return input_data

        def validate_args(self, **kwargs):
            pass

    validator = TestValidator(ValidatorMetadata(name="test_validator"))
    assert validator.name == "test_validator"


def test_base_plugin_repr():
    """Test Validator repr shows name and version."""

    class TestValidator(Validator):
        def execute(self, input_data, **kwargs):
            return input_data

        def validate_args(self, **kwargs):
            pass

    validator = TestValidator(ValidatorMetadata(name="test", version="2.0.0"))
    assert "TestValidator" in repr(validator)
    assert "test" in repr(validator)
    assert "2.0.0" in repr(validator)
