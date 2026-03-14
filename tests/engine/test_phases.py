"""Tests for pipeline phases — covers coercion, nullification, error reporting,
column resolution, and report generation paths.
"""

import polars as pl
import pytest

from nyctea import Registry, SchemaModel, register_builtins
from nyctea.engine.context import PipelineContext
from nyctea.engine.phases import (
    CoercionPhase,
)
from nyctea.engine.results import ErrorReportConfig
from nyctea.engine.utils import SchemaResolutionError, _resolve_dtype, resolve_column_names
from nyctea.exceptions import PipelineError


@pytest.fixture
def registry():
    reg = Registry()
    register_builtins(reg)
    return reg


@pytest.fixture
def simple_schema():
    return SchemaModel.from_dict(
        {
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": False,
                    "checks": [{"name": "between", "args": {"min": 0, "max": 150}}],
                },
                "name": {"dtype": "Utf8", "nullable": False},
            }
        }
    )


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
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age", "AGE"]}}})
        df = pl.DataFrame({"Age": [1, 2, 3]})
        result = resolve_column_names(schema, df)
        assert "age" in result.columns

    def test_missing_required_column_raises(self):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "required": True}}})
        df = pl.DataFrame({"name": ["Alice"]})
        with pytest.raises(SchemaResolutionError, match="Required column"):
            resolve_column_names(schema, df)

    def test_ambiguous_columns_raises(self):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["years"]}}})
        df = pl.DataFrame({"age": [1], "years": [2]})
        with pytest.raises(SchemaResolutionError, match="Ambiguous"):
            resolve_column_names(schema, df)

    def test_missing_optional_column_skipped(self):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "required": False}}})
        df = pl.DataFrame({"name": ["Alice"]})
        result = resolve_column_names(schema, df)
        assert result.columns == ["name"]

    def test_lazyframe_supported(self):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})
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
    def _context(self, schema, data):
        lf = data.lazy().with_row_index("__row_index__")
        return PipelineContext(
            data=lf,
            schema=schema,
            registry=Registry(),
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

    def test_coercion_with_failures(self):
        """Failed casts become null; pre-null masks track new nulls."""
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "null",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": ["25", "not_a_number", "30"]})
        ctx = self._context(schema, df)
        phase = CoercionPhase()
        result_ctx = phase.execute(ctx)
        collected = result_ctx.data.collect()
        ages = collected["age"].to_list()
        assert ages[0] == 25
        assert ages[1] is None
        assert ages[2] == 30
        # Pre-null mask tracks which nulls existed before coercion
        pre_null = collected["__pre_null__age"]
        new_nulls = collected["age"].is_null() & ~pre_null
        assert new_nulls.sum() == 1

    def test_per_column_coerce_override_true(self):
        """Column coerce=True overrides schema coerce=False."""
        schema = SchemaModel.from_dict(
            {
                "coerce": False,
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "coerce": True},
                    "name": {"dtype": "Utf8"},
                },
            }
        )
        df = pl.DataFrame({"age": ["25", "30"], "name": ["a", "b"]})
        ctx = self._context(schema, df)
        phase = CoercionPhase()
        result_ctx = phase.execute(ctx)
        collected = result_ctx.data.collect()
        assert collected["age"].dtype == pl.Int64
        assert collected["name"].dtype == pl.Utf8

    def test_per_column_coerce_override_false(self):
        """Column coerce=False overrides schema coerce=True."""
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "coerce": False},
                },
            }
        )
        df = pl.DataFrame({"age": ["25", "30"]})
        ctx = self._context(schema, df)
        phase = CoercionPhase()
        result_ctx = phase.execute(ctx)
        collected = result_ctx.data.collect()
        # age should stay as Utf8 because column coerce=False
        assert collected["age"].dtype == pl.Utf8

    def test_can_skip_mixed_coerce(self):
        """can_skip returns False if any column has coerce=True."""
        schema = SchemaModel.from_dict(
            {
                "coerce": False,
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "coerce": True},
                    "name": {"dtype": "Utf8"},
                },
            }
        )
        df = pl.DataFrame({"age": ["1"], "name": ["a"]})
        ctx = self._context(schema, df)
        phase = CoercionPhase()
        assert phase.can_skip(ctx) is False

    def test_can_skip_all_coerce_false(self):
        """can_skip returns True when schema and all columns have coerce=False."""
        schema = SchemaModel.from_dict(
            {
                "coerce": False,
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True},
                },
            }
        )
        df = pl.DataFrame({"age": ["1"]})
        ctx = self._context(schema, df)
        phase = CoercionPhase()
        assert phase.can_skip(ctx) is True

    def test_noop_when_dtype_matches(self):
        schema = SchemaModel.from_dict({"coerce": True, "columns": {"age": {"dtype": "Int64"}}})
        df = pl.DataFrame({"age": [25, 30, 40]})
        ctx = self._context(schema, df)
        phase = CoercionPhase()
        result_ctx = phase.execute(ctx)
        assert result_ctx.data.collect()["age"].to_list() == [25, 30, 40]


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

    @pytest.mark.skip(reason="Step 4: _build_report() stub returns empty columns")
    def test_check_failure_recorded(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "between", "args": {"min": 0, "max": 150}}],
                    },
                }
            }
        )
        df = pl.DataFrame({"age": [25, -5, 200]})
        result = schema.validate(df, registry)
        assert len(result.errors) > 0
        assert result.report.columns["age"].check_failures >= 2

    @pytest.mark.skip(reason="Step 5: nullable enforcement not yet in pipeline")
    def test_nullable_false_null_raises(self, registry):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": False}}})
        df = pl.DataFrame({"age": [1, None, 3]})
        with pytest.raises(PipelineError, match="nullable=False"):
            schema.validate(df, registry)

    def test_column_resolution_via_synonym(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "synonyms": ["Age"]},
                }
            }
        )
        df = pl.DataFrame({"Age": [25, 30]})
        result = schema.validate(df, registry)
        assert "age" in result.data.collect_schema().names()

    @pytest.mark.skip(reason="Step 4: _build_report() stub returns empty columns")
    def test_report_check_failure_counts(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "score": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    },
                }
            }
        )
        df = pl.DataFrame({"score": [10, -1, -2, 5]})
        result = schema.validate(df, registry)
        assert result.report.columns["score"].check_failures == 2

    def test_coerce_strict_incompatible_type_raises(self, registry):
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "columns": {"value": {"dtype": "Int64", "nullable": False}},
            }
        )
        df = pl.DataFrame({"value": ["hello", "world"]})
        with pytest.raises(PipelineError):
            schema.validate(df, registry)

    def test_coerce_null_on_failure(self, registry):
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "null",
                "columns": {"value": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"value": ["10", "bad", "20"]})
        result = schema.validate(df, registry)
        values = result.data.collect()["value"].to_list()
        assert values == [10, None, 20]


# ---------------------------------------------------------------------------
# Nullification (on_failure='null')
# ---------------------------------------------------------------------------


class TestNullification:
    @pytest.mark.skip(reason="Step 5: NullificationPhase not yet implemented")
    def test_failing_values_nullified(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "null",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                }
            }
        )
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
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        df = pl.DataFrame({"age": [1, -1, -2]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="summary"))
        assert "column" in result.errors.columns
        assert "check" in result.errors.columns
        assert "count" in result.errors.columns
        assert len(result.errors) == 1
        assert result.errors["count"].item() == 2

    def test_cells_mode_row_index(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        df = pl.DataFrame({"age": [1, -1, -2]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="cells"))
        assert "row_index" in result.errors.columns
        assert "value" in result.errors.columns
        assert len(result.errors) == 2
        assert result.errors["row_index"].to_list() == [1, 2]

    def test_rows_mode_row_indices(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        df = pl.DataFrame({"age": [1, -1, 5, -3]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="rows"))
        assert "row_indices" in result.errors.columns
        assert "count" in result.errors.columns
        assert result.errors["count"].item() == 2
        assert result.errors["row_indices"].to_list() == [[1, 3]]

    def test_limit_caps_error_rows(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        df = pl.DataFrame({"age": [-1, -2, -3, -4, -5]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="cells", limit=2))
        assert len(result.errors) == 2

    def test_limit_caps_rows_mode(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        df = pl.DataFrame({"age": [-1, -2, -3, -4, -5]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="rows", limit=3))
        assert len(result.errors["row_indices"].to_list()[0]) == 3
        # count still reflects total failures
        assert result.errors["count"].item() == 5

    def test_empty_errors_when_all_pass(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        df = pl.DataFrame({"age": [1, 2, 3]})
        for mode in ("summary", "rows", "cells"):
            result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode=mode))
            assert len(result.errors) == 0

    def test_multiple_checks_same_column(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [
                            {"name": "min_value", "args": {"min": 0}},
                            {"name": "between", "args": {"min": 0, "max": 100}},
                        ],
                    }
                }
            }
        )
        df = pl.DataFrame({"age": [-1, 50, 200]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="summary"))
        assert len(result.errors) == 2
        checks = result.errors["check"].to_list()
        assert "min_value" in checks
        assert "between" in checks


# ---------------------------------------------------------------------------
# ValidationReport.summary()
# ---------------------------------------------------------------------------


class TestValidationReportSummary:
    @pytest.mark.skip(reason="Step 4: _build_report() stub returns empty columns")
    def test_summary_with_failures(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        df = pl.DataFrame({"age": [10, -1, 5]})
        result = schema.validate(df, registry)
        text = result.report.summary()
        assert "Validation Report" in text
        assert "Check failures" in text

    def test_summary_all_valid(self, registry):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": True}}})
        df = pl.DataFrame({"age": [1, 2, 3]})
        result = schema.validate(df, registry)
        text = result.report.summary()
        assert "3/3 valid" in text


# ---------------------------------------------------------------------------
# on_failure behavior
# ---------------------------------------------------------------------------


class TestOnFailure:
    """Tests for the on_failure schema/column-level failure handling."""

    def test_schema_level_raise_is_default(self):
        schema = SchemaModel.from_dict(
            {
                "columns": {"age": {"dtype": "Int64"}},
            }
        )
        assert schema.on_failure == "raise"

    def test_schema_level_on_failure_set(self):
        schema = SchemaModel.from_dict(
            {
                "on_failure": "null",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        assert schema.on_failure == "null"

    def test_schema_level_ignore(self):
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {"age": {"dtype": "Int64"}},
            }
        )
        assert schema.on_failure == "ignore"

    def test_resolve_column_explicit_overrides_schema(self):
        schema = SchemaModel.from_dict(
            {
                "on_failure": "null",
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "on_failure": "raise"},
                },
            }
        )
        assert schema.resolve_on_failure("age") == "raise"

    def test_resolve_column_inherits_schema(self):
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {"age": {"dtype": "Int64"}},
            }
        )
        assert schema.resolve_on_failure("age") == "ignore"

    def test_resolve_null_guard_non_nullable(self):
        """on_failure=null falls back to raise for non-nullable columns."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "null",
                "columns": {"age": {"dtype": "Int64", "nullable": False}},
            }
        )
        assert schema.resolve_on_failure("age") == "raise"

    def test_column_on_failure_null_requires_nullable(self):
        """Setting on_failure=null on a non-nullable column is a schema error."""
        with pytest.raises(ValueError, match="nullable=True"):
            SchemaModel.from_dict(
                {
                    "columns": {
                        "age": {"dtype": "Int64", "nullable": False, "on_failure": "null"},
                    },
                }
            )

    def test_coercion_raise_on_failure(self, registry):
        """on_failure=raise + coercion failure raises PipelineError."""
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "raise",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": ["25", "not_a_number", "30"]})
        with pytest.raises(PipelineError, match="Coercion failed"):
            schema.validate(df, registry)

    def test_coercion_null_on_failure(self, registry):
        """on_failure=null + coercion failure becomes null."""
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "null",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": ["25", "not_a_number", "30"]})
        result = schema.validate(df, registry)
        values = result.data.collect()["age"].to_list()
        assert values == [25, None, 30]

    def test_per_column_override_mixed(self, registry):
        """Schema on_failure=null, but one column overrides to raise."""
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "null",
                "columns": {
                    "name": {"dtype": "Utf8", "nullable": False, "on_failure": "raise"},
                    "age": {"dtype": "Int64", "nullable": True},
                },
            }
        )
        # age has bad data but on_failure=null (inherited) — should succeed
        df = pl.DataFrame({"name": ["Alice", "Bob"], "age": ["25", "bad"]})
        result = schema.validate(df, registry)
        values = result.data.collect()["age"].to_list()
        assert values == [25, None]

    def test_per_column_raise_fails_while_schema_null(self, registry):
        """Column-level on_failure=raise overrides schema-level null."""
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "null",
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "on_failure": "raise"},
                },
            }
        )
        df = pl.DataFrame({"age": ["25", "not_a_number"]})
        with pytest.raises(PipelineError, match="Coercion failed"):
            schema.validate(df, registry)

    def test_report_on_failure_field(self, registry):
        """Report reflects the schema-level on_failure setting."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "null",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": [1, 2, 3]})
        result = schema.validate(df, registry)
        assert result.report.on_failure == "null"
        assert "on_failure: null" in result.report.summary()
