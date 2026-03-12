"""Tests for pipeline phases — covers coercion, nullification, error reporting,
column resolution, and report generation paths."""

import polars as pl
import pytest

from nyctea import Registry, SchemaModel, register_builtins
from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_standard_pipeline
from nyctea.engine.phases import (
    CoercionPhase,
    ColumnResolutionPhase,
    ReportGenerationPhase,
)
from nyctea.engine.results import ErrorReportConfig, ValidationReport
from nyctea.engine.utils import SchemaResolutionError, _resolve_dtype, resolve_column_names
from nyctea.exceptions import PipelineError, ValidationError


@pytest.fixture
def registry():
    reg = Registry()
    register_builtins(reg)
    return reg


@pytest.fixture
def simple_schema():
    return SchemaModel.from_dict({
        "columns": {
            "age": {"dtype": "Int64", "nullable": False, "checks": [{"name": "between", "args": {"min": 0, "max": 150}}]},
            "name": {"dtype": "Utf8", "nullable": False},
        }
    })


# ---------------------------------------------------------------------------
# resolve_column_names
# ---------------------------------------------------------------------------

class TestResolveColumnNames:
    def test_no_renaming_needed(self):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
        df = pl.DataFrame({"age": [1, 2, 3]})
        result = resolve_column_names(schema, df)
        assert result.columns == ["age"]

    def test_synonym_renaming(self):
        schema = SchemaModel.from_dict({
            "columns": {"age": {"dtype": "Int64", "synonyms": ["Age", "AGE"]}}
        })
        df = pl.DataFrame({"Age": [1, 2, 3]})
        result = resolve_column_names(schema, df)
        assert "age" in result.columns

    def test_missing_required_column_raises(self):
        schema = SchemaModel.from_dict({
            "columns": {"age": {"dtype": "Int64", "required": True}}
        })
        df = pl.DataFrame({"name": ["Alice"]})
        with pytest.raises(SchemaResolutionError, match="Required column"):
            resolve_column_names(schema, df)

    def test_ambiguous_columns_raises(self):
        schema = SchemaModel.from_dict({
            "columns": {"age": {"dtype": "Int64", "synonyms": ["years"]}}
        })
        df = pl.DataFrame({"age": [1], "years": [2]})
        with pytest.raises(SchemaResolutionError, match="Ambiguous"):
            resolve_column_names(schema, df)

    def test_missing_optional_column_skipped(self):
        schema = SchemaModel.from_dict({
            "columns": {"age": {"dtype": "Int64", "required": False}}
        })
        df = pl.DataFrame({"name": ["Alice"]})
        result = resolve_column_names(schema, df)
        assert result.columns == ["name"]

    def test_lazyframe_supported(self):
        schema = SchemaModel.from_dict({
            "columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}
        })
        lf = pl.LazyFrame({"Age": [1, 2]})
        result = resolve_column_names(schema, lf)
        assert "age" in result.collect_schema().names()


# ---------------------------------------------------------------------------
# _resolve_dtype
# ---------------------------------------------------------------------------

class TestResolveDtype:
    def test_polars_instance_passthrough(self):
        result = _resolve_dtype(pl.Int64())
        assert result == pl.Int64()

    def test_string_resolution(self):
        assert _resolve_dtype("Utf8") == pl.Utf8

    def test_unknown_string_raises(self):
        with pytest.raises(ValueError, match="Unknown dtype string"):
            _resolve_dtype("NotAType")

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported dtype specification"):
            _resolve_dtype(123)


# ---------------------------------------------------------------------------
# CoercionPhase
# ---------------------------------------------------------------------------

class TestCoercionPhase:
    def _context(self, schema, data, strategy="strict"):
        lf = data.lazy().with_row_index("__row_index__")
        return PipelineContext(
            data=lf,
            schema=schema,
            registry=Registry(),
            coerce_strategy=strategy,
        )

    def test_skipped_when_coerce_false(self, simple_schema):
        phase = CoercionPhase()
        simple_schema.coerce = False
        df = pl.DataFrame({"age": [1, 2], "name": ["a", "b"]})
        ctx = self._context(simple_schema, df)
        assert phase.can_skip(ctx) is True

    def test_not_skipped_when_coerce_true(self, simple_schema):
        phase = CoercionPhase()
        simple_schema.coerce = True
        df = pl.DataFrame({"age": [1, 2], "name": ["a", "b"]})
        ctx = self._context(simple_schema, df)
        assert phase.can_skip(ctx) is False

    def test_null_on_failure_strategy(self):
        schema = SchemaModel.from_dict({"coerce": True, "columns": {"age": {"dtype": "Int64"}}})
        df = pl.DataFrame({"age": ["25", "not_a_number", "30"]})
        ctx = self._context(schema, df, strategy="null_on_failure")
        phase = CoercionPhase()
        result_ctx = phase.execute(ctx)
        ages = result_ctx.data.collect()["age"].to_list()
        assert ages[0] == 25
        assert ages[1] is None
        assert ages[2] == 30
        assert result_ctx.coercion_failures.get("age", 0) == 1


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_valid_data_no_errors(self, simple_schema, registry):
        df = pl.DataFrame({"age": [25, 30, 40], "name": ["Alice", "Bob", "Carol"]})
        result = simple_schema.validate(df, registry)
        assert result.report.rows_processed == 3
        assert result.report.rows_valid == 3
        assert len(result.errors) == 0

    def test_check_failure_recorded(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {
                "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "between", "args": {"min": 0, "max": 150}}]},
            }
        })
        df = pl.DataFrame({"age": [25, -5, 200]})
        result = schema.validate(df, registry)
        assert len(result.errors) > 0
        assert result.report.columns["age"].check_failures >= 2

    def test_nullable_false_null_raises(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {"age": {"dtype": "Int64", "nullable": False}}
        })
        df = pl.DataFrame({"age": [1, None, 3]})
        with pytest.raises(PipelineError, match="nullable=False"):
            schema.validate(df, registry)

    def test_column_resolution_via_synonym(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {
                "age": {"dtype": "Int64", "nullable": True, "synonyms": ["Age"]},
            }
        })
        df = pl.DataFrame({"Age": [25, 30]})
        result = schema.validate(df, registry)
        assert "age" in result.data.collect_schema().names()

    def test_report_check_failure_counts(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {
                "score": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]},
            }
        })
        df = pl.DataFrame({"score": [10, -1, -2, 5]})
        result = schema.validate(df, registry)
        assert result.report.columns["score"].check_failures == 2

    def test_coerce_strict_incompatible_type_raises(self, registry):
        schema = SchemaModel.from_dict({
            "coerce": True,
            "columns": {"value": {"dtype": "Int64", "nullable": False}},
        })
        df = pl.DataFrame({"value": ["hello", "world"]})
        with pytest.raises(PipelineError):
            schema.validate(df, registry)

    def test_coerce_null_on_failure(self, registry):
        schema = SchemaModel.from_dict({
            "coerce": True,
            "columns": {"value": {"dtype": "Int64", "nullable": True}},
        })
        df = pl.DataFrame({"value": ["10", "bad", "20"]})
        result = schema.validate(df, registry, coerce_strategy="null_on_failure")
        values = result.data.collect()["value"].to_list()
        assert values == [10, None, 20]


# ---------------------------------------------------------------------------
# Nullification (on_failure='null')
# ---------------------------------------------------------------------------

class TestNullification:
    def test_failing_values_nullified(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "on_failure": "null",
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                }
            }
        })
        df = pl.DataFrame({"age": [10, -1, 5, -3]})
        result = schema.validate(df, registry)
        ages = result.data.collect()["age"].to_list()
        assert ages[1] is None
        assert ages[3] is None
        assert ages[0] == 10
        assert ages[2] == 5
        assert result.report.columns["age"].nullified == 2


# ---------------------------------------------------------------------------
# Error report modes
# ---------------------------------------------------------------------------

class TestErrorReporting:
    def test_summary_mode_count_columns(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {
                "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
            }
        })
        df = pl.DataFrame({"age": [1, -1, -2]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="summary"))
        assert "column" in result.errors.columns
        assert "count" in result.errors.columns

    def test_cells_mode_row_index(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {
                "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
            }
        })
        df = pl.DataFrame({"age": [1, -1, -2]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="cells"))
        assert "row_index" in result.errors.columns


# ---------------------------------------------------------------------------
# ValidationReport.summary()
# ---------------------------------------------------------------------------

class TestValidationReportSummary:
    def test_summary_with_failures(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {
                "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
            }
        })
        df = pl.DataFrame({"age": [10, -1, 5]})
        result = schema.validate(df, registry)
        text = result.report.summary()
        assert "Validation Report" in text
        assert "Check failures" in text

    def test_summary_all_valid(self, registry):
        schema = SchemaModel.from_dict({
            "columns": {"age": {"dtype": "Int64", "nullable": True}}
        })
        df = pl.DataFrame({"age": [1, 2, 3]})
        result = schema.validate(df, registry)
        text = result.report.summary()
        assert "3/3 valid" in text
