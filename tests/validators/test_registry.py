"""Tests for validator registry."""

import pytest

from nyctea.exceptions import RegistrationError
from nyctea.validators.base import ValidatorMetadata
from nyctea.validators.column import ColumnParser
from nyctea.validators.registry import Registry, ValidatorRegistry


class SampleParser(ColumnParser):
    """Test parser."""

    def __init__(self, name="test"):
        """Initialize with test metadata."""
        super().__init__(ValidatorMetadata(name=name, tags=["test"]))

    def execute(self, column, **kwargs):
        return column

    def validate_args(self, **kwargs):
        pass


def test_plugin_registry_creation():
    """Test creating a validator registry."""
    registry = ValidatorRegistry(ColumnParser)
    assert registry.validator_type == ColumnParser
    assert len(registry) == 0


def test_plugin_registry_register():
    """Test registering a validator."""
    registry = ValidatorRegistry(ColumnParser)
    validator = SampleParser()

    registry.register(validator)
    assert len(registry) == 1
    assert registry.has("test")


def test_plugin_registry_get():
    """Test getting a validator by name."""
    registry = ValidatorRegistry(ColumnParser)
    validator = SampleParser()
    registry.register(validator)

    retrieved = registry.get("test")
    assert retrieved is validator


def test_plugin_registry_get_nonexistent():
    """Test getting a nonexistent validator raises KeyError."""
    registry = ValidatorRegistry(ColumnParser)

    with pytest.raises(KeyError, match="No validator named 'missing'"):
        registry.get("missing")


def test_plugin_registry_collision_detection():
    """Test that duplicate names are rejected."""
    registry = ValidatorRegistry(ColumnParser)
    validator1 = SampleParser(name="duplicate")
    validator2 = SampleParser(name="duplicate")

    registry.register(validator1)

    with pytest.raises(RegistrationError, match="already registered"):
        registry.register(validator2)


def test_plugin_registry_type_validation():
    """Test that wrong validator types are rejected."""
    from nyctea.validators.base import ValidatorMetadata
    from nyctea.validators.frame import FrameParser

    class TestFrameParser(FrameParser):
        def execute(self, frame, **kwargs):
            return frame

        def validate_args(self, **kwargs):
            pass

    registry = ValidatorRegistry(ColumnParser)
    frame_validator = TestFrameParser(ValidatorMetadata(name="frame"))

    with pytest.raises(TypeError, match="Registry expects ColumnParser"):
        registry.register(frame_validator)


def test_plugin_registry_list_names():
    """Test listing validator names."""
    registry = ValidatorRegistry(ColumnParser)
    registry.register(SampleParser(name="a"))
    registry.register(SampleParser(name="c"))
    registry.register(SampleParser(name="b"))

    names = registry.list_names()
    assert names == ["a", "b", "c"]  # Should be sorted


def test_plugin_registry_list_all():
    """Test listing all validators."""
    registry = ValidatorRegistry(ColumnParser)
    p1 = SampleParser(name="one")
    p2 = SampleParser(name="two")

    registry.register(p1)
    registry.register(p2)

    all_validators = registry.list_all()
    assert len(all_validators) == 2
    assert p1 in all_validators
    assert p2 in all_validators


def test_plugin_registry_get_by_tag():
    """Test getting validators by tag."""

    class TaggedParser(ColumnParser):
        def __init__(self, name, tags):
            super().__init__(ValidatorMetadata(name=name, tags=tags))

        def execute(self, column, **kwargs):
            return column

        def validate_args(self, **kwargs):
            pass

    registry = ValidatorRegistry(ColumnParser)
    p1 = TaggedParser("p1", ["numeric", "validation"])
    p2 = TaggedParser("p2", ["string"])
    p3 = TaggedParser("p3", ["numeric"])

    registry.register(p1)
    registry.register(p2)
    registry.register(p3)

    numeric_validators = registry.get_by_tag("numeric")
    assert len(numeric_validators) == 2
    assert p1 in numeric_validators
    assert p3 in numeric_validators

    string_validators = registry.get_by_tag("string")
    assert len(string_validators) == 1
    assert p2 in string_validators


def test_master_registry_creation():
    """Test creating a master registry."""
    registry = Registry()

    assert registry.column_parsers is not None
    assert registry.column_checks is not None
    assert registry.frame_parsers is not None
    assert registry.frame_checks is not None


def test_master_registry_get_counts():
    """Test getting validator counts."""
    registry = Registry()

    counts = registry.get_validator_counts()
    assert counts["column_parsers"] == 0
    assert counts["column_checks"] == 0
    assert counts["frame_parsers"] == 0
    assert counts["frame_checks"] == 0

    # Register a parser
    registry.register_column_parser(SampleParser())
    counts = registry.get_validator_counts()
    assert counts["column_parsers"] == 1


def test_master_registry_repr():
    """Test master registry repr."""
    registry = Registry()
    repr_str = repr(registry)

    assert "Registry" in repr_str
    assert "column_parsers" in repr_str
