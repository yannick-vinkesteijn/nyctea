"""Tests for exception hierarchy."""

import pytest

from nyctea.exceptions import (
    ConfigurationError,
    NycteaError,
    PipelineError,
    PluginError,
    PluginExecutionError,
    RegistrationError,
    ValidationError,
)


def test_nyctea_error_is_base():
    """Test that NycteaError is the base exception."""
    assert issubclass(PluginError, NycteaError)
    assert issubclass(ValidationError, NycteaError)
    assert issubclass(PipelineError, NycteaError)
    assert issubclass(ConfigurationError, NycteaError)


def test_plugin_error_with_context():
    """Test PluginError stores context."""
    error = PluginError(
        "Test error",
        plugin_name="test_plugin",
        plugin_type="ColumnParser"
    )
    assert error.plugin_name == "test_plugin"
    assert error.plugin_type == "ColumnParser"
    assert str(error) == "Test error"


def test_registration_error_inherits_plugin_error():
    """Test RegistrationError is a PluginError."""
    assert issubclass(RegistrationError, PluginError)

    error = RegistrationError(
        "Registration failed",
        plugin_name="bad_plugin"
    )
    assert error.plugin_name == "bad_plugin"


def test_plugin_execution_error_with_column():
    """Test PluginExecutionError stores column and original error."""
    original = ValueError("Bad value")
    error = PluginExecutionError(
        "Execution failed",
        plugin_name="my_parser",
        column="age",
        original_error=original
    )
    assert error.column == "age"
    assert error.original_error is original
    assert error.plugin_name == "my_parser"


def test_validation_error_with_details():
    """Test ValidationError stores validation context."""
    error = ValidationError(
        "Validation failed",
        column="age",
        phase="column_checks",
        error_count=5
    )
    assert error.column == "age"
    assert error.phase == "column_checks"
    assert error.error_count == 5


def test_pipeline_error_with_phase():
    """Test PipelineError stores phase information."""
    error = PipelineError(
        "Pipeline failed",
        phase="column_parsing",
        pipeline_state="executing"
    )
    assert error.phase == "column_parsing"
    assert error.pipeline_state == "executing"


def test_configuration_error():
    """Test ConfigurationError can be raised."""
    with pytest.raises(ConfigurationError, match="Invalid config"):
        raise ConfigurationError("Invalid config")
