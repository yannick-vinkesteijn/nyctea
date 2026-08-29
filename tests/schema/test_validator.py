"""Tests for SchemaValidator: error report config, kwargs, and pipeline customization."""

import polars as pl
import pydantic
import pytest

from nyctea import Registry, SchemaModel, register_builtins
from nyctea.engine.results import ErrorReportConfig
from nyctea.schema.validator import SchemaValidator


@pytest.fixture
def registry():
    reg = Registry()
    register_builtins(reg)
    return reg


@pytest.fixture
def failing_schema():
    return SchemaModel.from_dict(
        {
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "on_failure": "ignore",
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                }
            }
        }
    )


def test_cells_mode_includes_value_by_default(failing_schema, registry):
    df = pl.DataFrame({"age": [1, -1]})
    result = failing_schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="cells"))
    assert "value" in result.errors.columns
    assert result.errors["value"].to_list() == ["-1"]


def test_cells_mode_omits_value_when_include_values_false(failing_schema, registry):
    df = pl.DataFrame({"age": [1, -1]})
    result = failing_schema.validate(
        df, registry, error_report_config=ErrorReportConfig(mode="cells", include_values=False)
    )
    assert "value" not in result.errors.columns
    assert result.errors["row_index"].to_list() == [1]


def test_cells_mode_omits_value_on_empty_result(failing_schema, registry):
    df = pl.DataFrame({"age": [1, 2]})
    result = failing_schema.validate(
        df, registry, error_report_config=ErrorReportConfig(mode="cells", include_values=False)
    )
    assert "value" not in result.errors.columns
    assert len(result.errors) == 0


def test_error_report_config_rejects_negative_limit():
    with pytest.raises(pydantic.ValidationError):
        ErrorReportConfig(limit=-1)


def test_validate_rejects_unknown_kwargs(failing_schema, registry):
    validator = SchemaValidator(failing_schema, registry)
    df = pl.DataFrame({"age": [1, 2]})
    with pytest.raises(TypeError):
        validator.validate(df, strict=True)  # ty: ignore[unknown-argument]


def test_schema_validate_rejects_unknown_kwargs(failing_schema, registry):
    df = pl.DataFrame({"age": [1, 2]})
    with pytest.raises(TypeError):
        failing_schema.validate(df, registry, strict=True)


def test_customize_pipeline_returns_independent_copy(failing_schema, registry):
    validator = SchemaValidator(failing_schema, registry)
    original_phase_count = len(validator.pipeline)

    copy = validator.customize_pipeline()
    assert copy is not validator.pipeline

    copy.remove_phase(copy.list_phases()[-1])

    assert len(copy) == original_phase_count - 1
    assert len(validator.pipeline) == original_phase_count
