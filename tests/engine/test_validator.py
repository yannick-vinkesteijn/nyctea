"""Tests for DataValidator: error report config, kwargs, and pipeline customization."""

import polars as pl
import pydantic
import pytest

from nyctea import Registry, SchemaModel, register_builtins
from nyctea.engine.results import ErrorReportConfig
from nyctea.engine.validator import DataValidator
from nyctea.exceptions import PipelineError


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


def test_cells_mode_omits_value_when_disabled(failing_schema, registry):
    df = pl.DataFrame({"age": [1, -1]})
    result = failing_schema.validate(
        df, registry, error_report_config=ErrorReportConfig(mode="cells", include_values=False)
    )
    assert "value" not in result.errors.columns
    assert result.errors["row_index"].to_list() == [1]


def test_cells_mode_omits_value_when_empty(failing_schema, registry):
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
    validator = DataValidator(failing_schema, registry)
    df = pl.DataFrame({"age": [1, 2]})
    with pytest.raises(TypeError):
        validator.validate(df, strict=True)  # ty: ignore[unknown-argument]


def test_schema_validate_rejects_unknown_kwargs(failing_schema, registry):
    df = pl.DataFrame({"age": [1, 2]})
    with pytest.raises(TypeError):
        failing_schema.validate(df, registry, strict=True)


def test_non_nullable_raises_bare_message(registry):
    """The not-null raise happens after the pipeline, so it is not phase-wrapped.

    #57 predicted this message change when the not-null enforcement moved out of
    `ColumnCheckPhase` and into the merged aggregate pass. That move has happened,
    and the message is user-visible and was unpinned. Phase 1.3 rewrites the raise
    loops that produce it.
    """
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": False}}})

    with pytest.raises(PipelineError) as exc:
        schema.validate(pl.DataFrame({"age": [1, None, 3]}), registry)

    assert str(exc.value) == "Column 'age' has nullable=False but contains null values."
    assert "Phase '" not in str(exc.value), "the raise is post-pipeline, so it must not be phase-wrapped"
