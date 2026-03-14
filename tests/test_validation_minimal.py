"""Test suite for minimal validation functionality with new plugin architecture."""

import polars as pl
import pytest

from nyctea import Registry, SchemaModel, register_builtins


@pytest.fixture
def sample_dataframe():
    """Create a simple test dataset."""
    return pl.DataFrame(
        {
            "name": ["  Alice  ", "  Bob  ", "  Charlie  "],
            "age": ["25", "30", "35"],
            "city": ["NYC", "LA", "SF"],
        }
    )


@pytest.fixture
def sample_schema():
    """Create a simple schema for testing."""
    return SchemaModel.from_dict(
        {
            "lazy": False,
            "coerce": False,
            "columns": {
                "name": {
                    "dtype": "Utf8",
                    "parsers": [
                        {"name": "strip"},
                        {"name": "lower"},
                    ],
                    "nullable": False,
                    "required": True,
                },
                "age": {
                    "dtype": "Int64",
                    "parsers": [
                        {"name": "strip"},
                        {"name": "to_int"},
                    ],
                    "checks": [
                        {"name": "min_value", "args": {"min": 0}},
                    ],
                    "nullable": False,
                    "required": True,
                },
                "city": {
                    "dtype": "Utf8",
                    "parsers": [
                        {"name": "strip"},
                        {"name": "upper"},
                    ],
                    "nullable": False,
                    "required": True,
                },
            },
        }
    )


@pytest.fixture
def registry():
    """Create and populate a registry with built-in plugins."""
    reg = Registry()
    register_builtins(reg)
    return reg


def test_schema_loads_successfully(sample_schema):
    """Test that schema loads with correct number of columns."""
    assert len(sample_schema.columns) == 3
    assert "name" in sample_schema.columns
    assert "age" in sample_schema.columns
    assert "city" in sample_schema.columns


def test_registry_has_plugins(registry):
    """Test that registry has expected built-in plugins."""
    counts = registry.get_plugin_counts()
    assert counts["column_parsers"] == 5
    assert counts["column_checks"] == 4
    assert counts["frame_parsers"] == 0
    assert counts["frame_checks"] == 0


def test_validation_succeeds(sample_dataframe, sample_schema, registry):
    """Test that basic validation succeeds."""
    result = sample_schema.validate(sample_dataframe, registry)

    assert result is not None
    assert result.data is not None
    assert result.errors is not None
    assert result.report is not None


def test_parsers_applied_correctly(sample_dataframe, sample_schema, registry):
    """Test that parsers transform data correctly."""
    result = sample_schema.validate(sample_dataframe, registry)

    # Check that strip and lower were applied to names
    assert result.data["name"].to_list() == ["alice", "bob", "charlie"]

    # Check that strip and to_int were applied to age
    assert result.data["age"].to_list() == [25, 30, 35]
    assert result.data["age"].dtype == pl.Int64

    # Check that strip and upper were applied to city
    assert result.data["city"].to_list() == ["NYC", "LA", "SF"]


def test_validation_report(sample_dataframe, sample_schema, registry):
    """Test that validation report is generated correctly."""
    result = sample_schema.validate(sample_dataframe, registry)

    assert result.report.rows_processed == 3
    assert result.report.rows_valid == 3
    assert result.report.on_failure == "raise"


def test_no_errors_on_valid_data(sample_dataframe, sample_schema, registry):
    """Test that no errors are reported for valid data."""
    result = sample_schema.validate(sample_dataframe, registry)

    # Errors DataFrame should be empty
    assert len(result.errors) == 0


def test_checks_validate(sample_dataframe, sample_schema, registry):
    """Test that checks run successfully."""
    result = sample_schema.validate(sample_dataframe, registry)

    # All ages should pass min_value check (>= 0)
    assert result.report.rows_valid == 3


def test_invalid_age_fails_check(sample_schema, registry):
    """Test that negative age fails min_value check."""
    df_invalid = pl.DataFrame(
        {
            "name": ["Alice"],
            "age": ["-5"],
            "city": ["NYC"],
        }
    )

    result = sample_schema.validate(df_invalid, registry)

    # Should have check failures
    assert len(result.errors) > 0
