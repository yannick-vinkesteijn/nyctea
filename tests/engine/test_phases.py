"""Tests for pipeline phases — covers coercion, nullification, error reporting,
column resolution, and report generation paths.
"""

import polars as pl
import pytest

from nyctea import Registry, SchemaModel, register_builtins
from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.phases import (
    COERCION_CHECK,
    NOT_NULL_CHECK,
    PARSING_CHECK,
    CoercionPhase,
    ColumnResolutionPhase,
)
from nyctea.engine.results import ErrorReportConfig
from nyctea.exceptions import PipelineError, ValidationError
from nyctea.utils import resolve_dtype
from nyctea.validators.decorators import ValidatorDecorator


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
# ColumnResolutionPhase
#
# Characterization tests for the production resolution path. Before #86 the
# three error paths (phases.py:116, 124, 134) had no coverage at all, because
# the only resolution tests exercised a duplicate implementation in
# engine/utils.py that no production code called. That duplicate is now deleted.
# ---------------------------------------------------------------------------


def _resolution_context(schema, data):
    """Build a context positioned exactly as ColumnResolutionPhase expects it."""
    return PipelineContext(data=data.lazy(), schema=schema, registry=Registry())


def test_resolution_phase_renames_synonym_to_canonical():
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})
    ctx = _resolution_context(schema, pl.DataFrame({"Age": [1, 2]}))

    result = ColumnResolutionPhase().execute(ctx)

    assert result.data.collect_schema().names() == ["age"]


def test_resolution_phase_sets_original_data():
    """original_data is the post-resolution snapshot the report's null stats read from."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})
    ctx = _resolution_context(schema, pl.DataFrame({"Age": [1, 2]}))

    result = ColumnResolutionPhase().execute(ctx)

    assert result.original_data is not None
    assert result.original_data.collect_schema().names() == ["age"]


def test_resolution_leaves_frame_untouched():
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    ctx = _resolution_context(schema, pl.DataFrame({"age": [1, 2]}))

    result = ColumnResolutionPhase().execute(ctx)

    assert result.data.collect_schema().names() == ["age"]


def test_resolution_phase_skips_missing_optional_column():
    schema = SchemaModel.from_dict(
        {"columns": {"age": {"dtype": "Int64", "required": False}, "name": {"dtype": "Utf8"}}}
    )
    ctx = _resolution_context(schema, pl.DataFrame({"name": ["Alice"]}))

    result = ColumnResolutionPhase().execute(ctx)

    assert result.data.collect_schema().names() == ["name"]


def test_resolution_raises_on_missing_column():
    """Covers phases.py:116."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "required": True}}})
    ctx = _resolution_context(schema, pl.DataFrame({"name": ["Alice"]}))

    with pytest.raises(ValidationError, match="Required column 'age' is missing") as exc:
        ColumnResolutionPhase().execute(ctx)

    assert exc.value.column == "age"
    assert exc.value.phase == "column_resolution"


def test_resolution_raises_on_ambiguous_names():
    """Covers phases.py:124. Two accepted names for one column is ambiguous, not a preference."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["years"]}}})
    ctx = _resolution_context(schema, pl.DataFrame({"age": [1], "years": [2]}))

    with pytest.raises(ValidationError, match="Ambiguous columns for 'age'") as exc:
        ColumnResolutionPhase().execute(ctx)

    assert exc.value.column == "age"
    assert exc.value.phase == "column_resolution"


def test_resolution_rejects_colliding_physical_names():
    """A schema that could produce this is now rejected before any data is touched.

    Two columns claiming one name used to construct fine and fail here at
    runtime, and only if the data happened to contain the contested name. See
    test_name_ownership.py; the runtime guard is gone because it is unreachable.
    """
    with pytest.raises(ValueError, match="exactly one owner"):
        SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "synonyms": ["x"]},
                    "years": {"dtype": "Int64", "synonyms": ["x"]},
                }
            }
        )


def test_resolution_independent_of_column_order():
    """Column order must not affect resolution (#86 invariant 4)."""
    schema = SchemaModel.from_dict(
        {"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}, "name": {"dtype": "Utf8"}}}
    )
    forward = _resolution_context(schema, pl.DataFrame({"Age": [1], "name": ["a"]}))
    reverse = _resolution_context(schema, pl.DataFrame({"name": ["a"], "Age": [1]}))

    forward_names = ColumnResolutionPhase().execute(forward).data.collect_schema().names()
    reverse_names = ColumnResolutionPhase().execute(reverse).data.collect_schema().names()

    assert sorted(forward_names) == sorted(reverse_names) == ["age", "name"]


# ---------------------------------------------------------------------------
# _resolve_dtype
# ---------------------------------------------------------------------------


class TestResolveDtype:
    def test_polars_instance_passthrough(self):
        result = resolve_dtype(pl.Int64())
        assert result == pl.Int64()

    def test_string_resolution(self):
        assert resolve_dtype("Utf8") == pl.Utf8

    def test_unknown_string_raises(self):
        with pytest.raises(ValueError, match="Unknown dtype string"):
            resolve_dtype("NotAType")

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported dtype specification"):
            resolve_dtype(123)


# ---------------------------------------------------------------------------
# Public check-name contract
# ---------------------------------------------------------------------------


class TestPublicCheckNameContract:
    def test_not_null_check_name_is_frozen(self):
        assert NOT_NULL_CHECK == "not_null"

    def test_coercion_check_name_is_frozen(self):
        assert COERCION_CHECK == "coerce"

    def test_parsing_check_name_is_frozen(self):
        assert PARSING_CHECK == "parse"


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

    def _coerce_schema(self, coerce):
        return SchemaModel.from_dict(
            {"coerce": coerce, "columns": {"age": {"dtype": "Int64"}, "name": {"dtype": "Utf8"}}}
        )

    def test_skipped_when_coerce_false(self):
        phase = CoercionPhase()
        df = pl.DataFrame({"age": [1, 2], "name": ["a", "b"]})
        ctx = self._context(self._coerce_schema(False), df)
        assert phase.can_skip(ctx) is True

    def test_not_skipped_when_coerce_true(self):
        phase = CoercionPhase()
        df = pl.DataFrame({"age": [1, 2], "name": ["a", "b"]})
        ctx = self._context(self._coerce_schema(True), df)
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
# Collect count regression (#38)
# ---------------------------------------------------------------------------


def test_aggregates_use_one_collect(registry, collect_calls):
    """_run_aggregates_and_raise must perform a single aggregate collect covering
    on_failure=raise counts, on_failure=null counts, and report aggregates. _build_errors
    keeps its own collect, since row/cell modes need the default engine (see
    TestCollectEngineSelection).
    """
    schema = SchemaModel.from_dict(
        {
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "on_failure": "null",
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                },
                "score": {
                    "dtype": "Int64",
                    "nullable": True,
                    "on_failure": "raise",
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                },
            }
        }
    )
    df = pl.DataFrame({"age": [1, -1], "score": [1, 2]})
    schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="summary"))
    assert len(collect_calls) == 2


def test_collect_count_minimal_schema(registry, collect_calls):
    """No raise/null columns: only _build_errors and _build_report should collect."""
    schema = SchemaModel.from_dict(
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
    df = pl.DataFrame({"age": [1, -1]})
    schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="summary"))
    assert len(collect_calls) == 2


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

    def test_collect_count_bounded(self, simple_schema, registry, collect_calls):
        """#11/#38: guards against silently regaining wasted collects.

        2 today: _run_aggregates_and_raise (parser/coercion/not-null/check raise
        counts, on_failure=null counts, and report aggregates) and _build_errors.
        Update this count deliberately if it changes.
        """
        df = pl.DataFrame({"age": [25, 30, 40], "name": ["Alice", "Bob", "Carol"]})
        simple_schema.validate(df, registry)

        assert len(collect_calls) == 2

    def test_collect_count_bounded_with_coercion(self, registry, collect_calls):
        """Same guard as above, but for the path with coercion's own raise-check active.

        2 today: _run_aggregates_and_raise and _build_errors. The issue this
        guards against (#11) specifically called out that this path, not the
        no-coercion one, is the one most likely to regain a collect.
        """
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": False,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": ["10", "20", "30"]})
        schema.validate(df, registry)

        assert len(collect_calls) == 2

    def test_small_df_uses_default_engine(self, simple_schema, registry, collect_calls):
        """Below schema.streaming_row_threshold, an eager DataFrame stays on the
        default engine -- streaming's fixed setup cost regresses small validations.
        """
        df = pl.DataFrame({"age": [25, 30, 40], "name": ["Alice", "Bob", "Carol"]})
        simple_schema.validate(df, registry)

        assert collect_calls
        assert all(call.get("engine") == "in-memory" for call in collect_calls)

    def test_large_df_streams(self, registry, collect_calls):
        schema = SchemaModel.from_dict(
            {
                "streaming_row_threshold": 10,
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": list(range(20))})
        schema.validate(df, registry)

        assert collect_calls
        assert all(call.get("engine") == "streaming" for call in collect_calls)

    def test_lazyframe_input_streams(self, registry, collect_calls):
        """Unknown size (no free row count), and choosing lazy signals larger intent."""
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": True}}})
        lf = pl.LazyFrame({"age": [1, 2, 3]})
        schema.validate(lf, registry)

        assert collect_calls
        assert all(call.get("engine") == "streaming" for call in collect_calls)

    @pytest.mark.parametrize("mode", ["rows", "cells"])
    def test_rows_cells_no_engine_override(self, registry, collect_calls, mode):
        """#11 step 4: only pure reductions get an explicit engine.

        The rows/cells error builders materialize row indices and failing values, so
        they call plain _collect() with no engine kwarg even when the frame is well
        above streaming_row_threshold and every aggregate around them is streaming.
        Absence of the kwarg is the contract: it leaves those two on Polars' own
        engine="auto" selection, which follows global affinity. It does not mean they
        can never stream.
        """
        schema = SchemaModel.from_dict(
            {
                "streaming_row_threshold": 10,
                "on_failure": "ignore",
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                },
            }
        )
        df = pl.DataFrame({"age": [*range(19), -1]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode=mode))

        assert len(result.errors) == 1
        engines = [call.get("engine") for call in collect_calls]
        assert "streaming" in engines, "the aggregate collects should still stream above the threshold"
        assert None in engines, "the row/cell materialization should use the default engine"

    def test_check_failure_recorded(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "between", "args": {"min": 0, "max": 150}}],
                    },
                }
            }
        )
        df = pl.DataFrame({"age": [25, -5, 200]})
        result = schema.validate(df, registry)
        assert len(result.errors) > 0
        assert result.report.columns["age"].check_failures >= 2

    def test_nullable_false_null_raises(self, registry):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": False}}})
        df = pl.DataFrame({"age": [1, None, 3]})
        with pytest.raises(PipelineError, match="nullable=False"):
            schema.validate(df, registry)

    def test_nullable_false_leaks_no_internals(self, registry):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": False}}})
        df = pl.DataFrame({"age": [1, 2, 3]})
        result = schema.validate(df, registry)
        assert result.data.collect_schema().names() == ["age"]

    def test_nullable_false_skips_missing_optional_column(self, registry):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": False, "required": False}}})
        df = pl.DataFrame({"other": [1, 2, 3]})
        result = schema.validate(df, registry)
        assert "age" not in result.data.collect_schema().names()

    def test_parser_skips_missing_optional_column(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "id": {"dtype": "Int64"},
                    "name": {
                        "dtype": "Utf8",
                        "required": False,
                        "parsers": [{"name": "strip"}],
                    },
                }
            }
        )
        result = schema.validate(pl.DataFrame({"id": [1]}), registry)
        assert result.data.collect_schema().names() == ["id"]

    def test_parser_runs_for_present_optional_column(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "name": {
                        "dtype": "Utf8",
                        "required": False,
                        "parsers": [{"name": "strip"}],
                    }
                }
            }
        )
        result = schema.validate(pl.DataFrame({"name": [" Alice "]}), registry, lazy=False)
        assert result.data["name"].to_list() == ["Alice"]

    def test_check_skips_missing_optional_column(self, registry):
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {
                    "id": {"dtype": "Int64"},
                    "age": {
                        "dtype": "Int64",
                        "required": False,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    },
                },
            }
        )
        result = schema.validate(pl.DataFrame({"id": [1]}), registry)
        assert result.errors.is_empty()

    def test_check_runs_for_present_optional_column(self, registry):
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "required": False,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        result = schema.validate(pl.DataFrame({"age": [-1]}), registry)
        assert result.errors["count"].item() == 1

    def test_nullable_false_ignore_does_not_raise(self, registry):
        schema = SchemaModel.from_dict(
            {"columns": {"age": {"dtype": "Int64", "nullable": False, "on_failure": "ignore"}}}
        )
        df = pl.DataFrame({"age": [1, None, 3]})
        result = schema.validate(df, registry)
        assert result.data.collect_schema().names() == ["age"]

    def test_nullable_false_ignore_reports_null(self, registry):
        """on_failure='ignore' must report the null, not swallow it."""
        schema = SchemaModel.from_dict(
            {"columns": {"age": {"dtype": "Int64", "nullable": False, "on_failure": "ignore"}}}
        )
        df = pl.DataFrame({"age": [1, None, 3]})
        result = schema.validate(df, registry)
        assert result.errors.filter(pl.col("check") == "not_null")["count"].item() == 1

    def test_notnull_mask_alias_collision_raises(self, registry):
        """A real column named like the generated mask must error, not be silently dropped."""
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": False},
                    "__notnull__age": {"dtype": "Int64", "nullable": True},
                }
            }
        )
        df = pl.DataFrame({"age": [1, 2], "__notnull__age": [9, 9]})
        with pytest.raises(PipelineError, match="already contains a column named"):
            schema.validate(df, registry)

    def test_notnull_alias_collides_with_optional(self, registry):
        """A `__notnull__` alias is taken by a declared optional column that this frame omits."""
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": False},
                    "__notnull__age": {
                        "dtype": "Boolean",
                        "nullable": True,
                        "required": False,
                    },
                }
            }
        )

        with pytest.raises(PipelineError, match="schema already contains a column named"):
            schema.validate(pl.DataFrame({"age": [1]}), registry)

    def test_notnull_alias_collides_with_synonym(self, registry):
        """A `__notnull__` alias is taken by another column's schema synonym."""
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": False},
                    "flag": {
                        "dtype": "Boolean",
                        "nullable": True,
                        "required": False,
                        "synonyms": ["__notnull__age"],
                    },
                }
            }
        )

        with pytest.raises(PipelineError, match="schema already contains a column named"):
            schema.validate(pl.DataFrame({"age": [1]}), registry)

    def test_from_python_preserves_subclass(self):
        """from_python must honour the receiving class, not hardcode SchemaModel."""

        class MySchema(SchemaModel):
            pass

        result = MySchema.from_python({"columns": {"age": {"dtype": "Int64"}}})
        assert isinstance(result, MySchema)

    def test_user_prefixed_columns_are_preserved(self, registry):
        """Only columns this run generated are stripped, not everything matching a prefix."""
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": True}}})
        df = pl.DataFrame({"age": [1, 2], "__notnull__zzz": [7, 8], "__check__foo": [1, 2]})
        result = schema.validate(df, registry)
        assert result.data.collect_schema().names() == ["age", "__notnull__zzz", "__check__foo"]

    @pytest.mark.parametrize("declaration", ["input", "canonical", "synonym"])
    def test_row_index_alias_collision_raises(self, registry, declaration):
        columns = {"age": {"dtype": "Int64", "nullable": True}}
        data = {"age": [1]}
        if declaration == "canonical":
            columns["__row_index__"] = {
                "dtype": "UInt32",
                "nullable": True,
                "required": False,
            }
        elif declaration == "synonym":
            columns["id"] = {
                "dtype": "UInt32",
                "nullable": True,
                "required": False,
                "synonyms": ["__row_index__"],
            }
        else:
            data["__row_index__"] = [0]
        schema = SchemaModel.from_dict({"columns": columns})

        with pytest.raises(PipelineError, match="already contains a column named"):
            schema.validate(pl.DataFrame(data), registry)

    def test_generated_masks_are_still_stripped(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": False, "checks": [{"name": "min_value", "args": {"min": 0}}]}
                }
            }
        )
        result = schema.validate(pl.DataFrame({"age": [1, 2]}), registry)
        assert result.data.collect_schema().names() == ["age"]

    def test_pre_null_mask_alias_collision_raises(self, registry):
        """Same guard for the coercion pre-null snapshot."""
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True},
                    "__pre_null__age": {"dtype": "Int64", "nullable": True},
                }
            }
        )
        df = pl.DataFrame({"age": ["1", "2"], "__pre_null__age": [9, 9]})
        with pytest.raises(PipelineError, match="already contains a column named"):
            schema.validate(df, registry)

    @pytest.mark.parametrize("alias", ["__pre_null__age", "__coercion_ok__age"])
    def test_coercion_alias_collides_with_optional(self, registry, alias):
        """A coercion alias is taken by a declared optional column that this frame omits."""
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True},
                    alias: {
                        "dtype": "Boolean",
                        "nullable": True,
                        "required": False,
                    },
                }
            }
        )

        with pytest.raises(PipelineError, match="schema already contains a column named"):
            schema.validate(pl.DataFrame({"age": ["1"]}), registry)

    def test_duplicate_check_name_raises(self, registry):
        """Two same-named checks collided in check_masks and the second silently won.

        The first check was dropped from reporting AND enforcement: a declared
        between(0, 5) with on_failure='raise' let value 30 through and the report
        claimed 2/2 rows valid.
        """
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "a": {
                        "dtype": "Int64",
                        "on_failure": "raise",
                        "checks": [
                            {"name": "between", "args": {"min": 0, "max": 5}},
                            {"name": "between", "args": {"min": 0, "max": 100}},
                        ],
                    }
                }
            }
        )
        with pytest.raises(PipelineError, match="more than one check named 'between'"):
            schema.validate(pl.DataFrame({"a": [1, 30]}), registry)

    def test_same_check_name_on_two_columns(self, registry):
        """The key is (column, check), so the same check name on two columns must still work."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {
                    "a": {"dtype": "Int64", "checks": [{"name": "min_value", "args": {"min": 0}}]},
                    "b": {"dtype": "Int64", "checks": [{"name": "min_value", "args": {"min": 10}}]},
                },
            }
        )
        result = schema.validate(pl.DataFrame({"a": [1, -1], "b": [50, 5]}), registry)
        assert sorted(result.errors["column"].to_list()) == ["a", "b"]

    def test_not_null_reserved_on_non_nullable(self, registry):
        """A user check named not_null must not silently replace the built-in constraint."""
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="not_null", tags=[])
        def over_hundred(column: pl.Expr) -> pl.Expr:
            return column > 100

        schema = SchemaModel.from_dict(
            {"columns": {"age": {"dtype": "Int64", "nullable": False, "checks": [{"name": "not_null"}]}}}
        )
        with pytest.raises(PipelineError, match="reserved"):
            schema.validate(pl.DataFrame({"age": [1, 300]}), registry)

    def test_not_null_reserved_on_nullable(self, registry):
        """The name stays reserved because downstream consumers always treat it as internal."""
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="not_null", tags=[])
        def over_hundred(column: pl.Expr) -> pl.Expr:
            return column > 100

        schema = SchemaModel.from_dict(
            {"columns": {"age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "not_null"}]}}}
        )
        with pytest.raises(PipelineError, match="reserved"):
            schema.validate(pl.DataFrame({"age": [1, 300]}), registry)

    @pytest.mark.parametrize("mode", ["summary", "rows", "cells"])
    def test_not_null_in_every_error_mode(self, registry, mode):
        """Registering not-null masks must not break any error report mode."""
        schema = SchemaModel.from_dict(
            {"on_failure": "ignore", "columns": {"age": {"dtype": "Int64", "nullable": False}}}
        )
        result = schema.validate(
            pl.DataFrame({"age": [1, None, 3]}),
            registry,
            error_report_config=ErrorReportConfig(mode=mode),
        )
        assert result.errors.filter(pl.col("check") == "not_null").height == 1

    def test_check_mask_alias_collision_raises(self, registry):
        """Same guard for check masks."""
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "min_value", "args": {"min": 0}}]},
                    "__check__0": {"dtype": "Int64", "nullable": True},
                }
            }
        )
        df = pl.DataFrame({"age": [1, 2], "__check__0": [9, 9]})
        with pytest.raises(PipelineError, match="already contains a column named"):
            schema.validate(df, registry)

    def test_check_alias_collides_with_optional(self, registry):
        """A `__check__` alias is taken by a declared optional column that this frame omits."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    },
                    "__check__0": {
                        "dtype": "Boolean",
                        "nullable": True,
                        "required": False,
                    },
                },
            }
        )

        with pytest.raises(PipelineError, match="schema already contains a column named"):
            schema.validate(pl.DataFrame({"age": [1]}), registry)

    def test_check_alias_collision_under_coercion(self, registry):
        """A pre-seeded coercion mask must not shift the check-mask alias counter.

        Otherwise the first real check gets '__check__1' instead of '__check__0',
        and a user column literally named '__check__0' slips past this guard.
        """
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    },
                    "__check__0": {"dtype": "Int64", "nullable": True},
                },
            }
        )
        df = pl.DataFrame({"age": ["1", "2"], "__check__0": [9, 9]})
        with pytest.raises(PipelineError, match="already contains a column named"):
            schema.validate(df, registry)

    def test_check_mask_aliases_are_unambiguous(self, registry):
        """Column and check names containing '__' must not produce a shared alias.

        Column 'a' with check 'b__c' and column 'a__b' with check 'c' both mapped to
        '__check__a__b__c' under the old naming, which crashed polars.
        """
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="b__c", tags=[])
        def positive(column: pl.Expr) -> pl.Expr:
            return column > 0

        @decorators.column_check(name="c", tags=[])
        def over_thousand(column: pl.Expr) -> pl.Expr:
            return column > 1000

        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "a": {"dtype": "Int64", "nullable": True, "on_failure": "ignore", "checks": [{"name": "b__c"}]},
                    "a__b": {"dtype": "Int64", "nullable": True, "on_failure": "ignore", "checks": [{"name": "c"}]},
                }
            }
        )
        result = schema.validate(pl.DataFrame({"a": [5, -1], "a__b": [1, 2]}), registry)
        errors = result.errors
        assert errors.filter((pl.col("column") == "a") & (pl.col("check") == "b__c"))["count"].item() == 1
        assert errors.filter((pl.col("column") == "a__b") & (pl.col("check") == "c"))["count"].item() == 2

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

    def test_report_check_failure_counts(self, registry):
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "score": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    },
                }
            }
        )
        df = pl.DataFrame({"score": [10, -1, -2, 5]})
        result = schema.validate(df, registry)
        assert result.report.columns["score"].check_failures == 2

    def test_two_failing_checks_count_twice(self, registry):
        """A row failing two checks on the same column must count as two failures.

        report.columns[col].check_failures must equal the sum of errors["count"]
        for that column, not the count of distinct failing rows.
        """
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [
                            {"name": "min_value", "args": {"min": 0}},
                            {"name": "between", "args": {"min": 0, "max": 100}},
                        ],
                    },
                },
            }
        )
        df = pl.DataFrame({"age": [50, -1, 200]})
        result = schema.validate(df, registry)
        errors_sum = result.errors.filter(pl.col("column") == "age")["count"].sum()
        assert errors_sum == 3
        assert result.report.columns["age"].check_failures == errors_sum
        assert result.report.rows_valid == 1

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


@pytest.mark.parametrize("mode", ["summary", "rows", "cells"])
@pytest.mark.parametrize("on_failure", ["ignore", "null"])
def test_parser_introduced_null_is_reported(registry, mode, on_failure):
    schema = SchemaModel.from_dict(
        {
            "on_failure": on_failure,
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "to_int"}],
                }
            },
        }
    )

    result = schema.validate(
        pl.DataFrame({"age": ["1", "bad", None]}),
        registry,
        error_report_config=ErrorReportConfig(mode=mode),
        lazy=False,
    )

    assert isinstance(result.data, pl.DataFrame)
    assert result.data["age"].to_list() == [1, None, None]
    parse_errors = result.errors.filter(pl.col("check") == PARSING_CHECK)
    assert parse_errors.height == 1
    if mode != "cells":
        assert parse_errors["count"].item() == 1
    else:
        assert parse_errors["value"].item() == "bad"
    assert result.report.rows_processed == 3
    assert result.report.rows_valid == 2
    assert result.report.columns["age"].parse_failures == 1
    assert result.report.columns["age"].coercion_failures == 0
    assert result.report.columns["age"].check_failures == 0
    assert result.report.columns["age"].original_null_count == 1
    assert result.report.columns["age"].final_null_count == 2
    assert "Parse failures: 1" in result.report.summary()


def test_parser_introduced_null_raises(registry):
    schema = SchemaModel.from_dict(
        {
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "to_int"}],
                }
            }
        }
    )

    with pytest.raises(PipelineError, match="Parsing failed for column 'age'"):
        schema.validate(pl.DataFrame({"age": ["1", "bad"]}), registry)


def test_parser_null_precedes_not_null(registry):
    schema = SchemaModel.from_dict(
        {
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": False,
                    "parsers": [{"name": "to_int"}],
                }
            }
        }
    )

    with pytest.raises(PipelineError, match="Parsing failed for column 'age'"):
        schema.validate(pl.DataFrame({"age": ["1", "bad"]}), registry)


def test_parser_chain_uses_prior_null_state(registry):
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "strip"}, {"name": "to_int"}],
                }
            },
        }
    )

    result = schema.validate(pl.DataFrame({"age": [" 1 ", " invalid "]}), registry, lazy=False)

    assert isinstance(result.data, pl.DataFrame)
    assert result.data["age"].to_list() == [1, None]
    assert result.report.columns["age"].parse_failures == 1


def test_original_nulls_counted_before_frame_parsing(registry):
    decorators = ValidatorDecorator(registry)

    @decorators.frame_parser(name="drop_nulls", preserve_columns=True, preserve_rows=False)
    def drop_nulls(frame: pl.LazyFrame) -> pl.LazyFrame:
        return frame.filter(pl.col("age").is_not_null())

    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "frame_parsers": [{"name": "drop_nulls"}],
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "to_int"}],
                }
            },
        }
    )

    result = schema.validate(pl.DataFrame({"age": [None, "1"]}), registry)

    assert result.report.rows_processed == 1
    assert result.report.columns["age"].original_null_count == 1
    assert result.report.columns["age"].parse_failures == 0


@pytest.mark.parametrize("input_kind", ["eager", "lazy"])
@pytest.mark.parametrize("output_lazy", [False, True])
def test_null_provenance_has_eager_lazy_parity(registry, input_kind, output_lazy):
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "to_int"}],
                }
            },
        }
    )
    data = pl.DataFrame({"age": ["1", "bad", None]})
    input_data = data if input_kind == "eager" else data.lazy()

    result = schema.validate(input_data, registry, lazy=output_lazy)

    assert result.report.columns["age"].parse_failures == 1
    assert result.report.columns["age"].original_null_count == 1
    assert result.report.columns["age"].final_null_count == 2


def test_original_null_count_handles_empty_data(registry):
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "to_int"}],
                }
            },
        }
    )

    result = schema.validate(pl.DataFrame({"age": []}, schema={"age": pl.String}), registry)

    assert result.report.rows_processed == 0
    assert result.report.rows_valid == 0
    assert result.report.columns["age"].parse_failures == 0
    assert result.report.columns["age"].original_null_count == 0
    assert result.report.columns["age"].final_null_count == 0


def test_original_null_count_without_column_parsers(registry):
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {"age": {"dtype": "Int64", "nullable": True}},
        }
    )

    result = schema.validate(pl.DataFrame({"age": [1, None]}), registry)

    assert result.report.columns["age"].original_null_count == 1
    assert result.report.columns["age"].final_null_count == 1


def test_original_nulls_use_resolved_name(registry):
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "synonyms": ["Age"],
                }
            },
        }
    )

    result = schema.validate(pl.DataFrame({"Age": [1, None]}), registry)

    assert result.report.columns["age"].original_null_count == 1


def test_parse_check_name_is_reserved(registry):
    decorators = ValidatorDecorator(registry)

    @decorators.column_check(name="parse", tags=[])
    def fake_parse(column: pl.Expr) -> pl.Expr:
        return column > 0

    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "checks": [{"name": "parse"}],
                }
            },
        }
    )

    with pytest.raises(PipelineError, match="reserved"):
        schema.validate(pl.DataFrame({"age": [1]}), registry)


@pytest.mark.parametrize(
    "alias",
    ["__pre_parse_null__age", "__pre_parse_value__age", "__parse_ok__age"],
)
def test_parser_mask_alias_collision_raises(registry, alias):
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "to_int"}],
                },
                alias: {"dtype": "Int64", "nullable": True},
            },
        }
    )

    with pytest.raises(PipelineError, match="already contains a column named"):
        schema.validate(
            pl.DataFrame({"age": ["1"], alias: [1]}),
            registry,
            error_report_config=ErrorReportConfig(mode="cells"),
        )


@pytest.mark.parametrize(
    "alias",
    ["__pre_parse_null__age", "__pre_parse_value__age", "__parse_ok__age"],
)
def test_parser_alias_collides_with_optional(registry, alias):
    """A parser alias is taken by a declared optional column that this frame omits."""
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "parsers": [{"name": "to_int"}],
                },
                alias: {
                    "dtype": "Int64",
                    "nullable": True,
                    "required": False,
                },
            },
        }
    )

    with pytest.raises(PipelineError, match="schema already contains a column named"):
        schema.validate(
            pl.DataFrame({"age": ["1"]}),
            registry,
            error_report_config=ErrorReportConfig(mode="cells"),
        )


def test_parser_failure_distinct_from_original_null(registry):
    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": False,
                    "parsers": [{"name": "to_int"}],
                }
            },
        }
    )

    result = schema.validate(pl.DataFrame({"age": ["1", "bad", None]}), registry)

    assert result.errors.filter(pl.col("check") == PARSING_CHECK)["count"].item() == 1
    assert result.errors.filter(pl.col("check") == NOT_NULL_CHECK)["count"].item() == 2
    assert result.report.rows_valid == 1
    assert result.report.columns["age"].parse_failures == 1
    assert result.report.columns["age"].check_failures == 2
    assert result.report.columns["age"].original_null_count == 1


# ---------------------------------------------------------------------------
# Frame-level parsers/checks (#8)
# ---------------------------------------------------------------------------


class TestFrameValidators:
    def test_frame_parser_runs_and_transforms_data(self, registry):
        decorators = ValidatorDecorator(registry)

        @decorators.frame_parser(name="add_total", preserve_columns=False, preserve_rows=True)
        def add_total(frame: pl.LazyFrame) -> pl.LazyFrame:
            return frame.with_columns((pl.col("a") + pl.col("b")).alias("total"))

        schema = SchemaModel.from_dict(
            {
                "frame_parsers": [{"name": "add_total"}],
                "columns": {"a": {"dtype": "Int64"}, "b": {"dtype": "Int64"}},
            }
        )
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = schema.validate(df, registry)
        assert result.data.collect()["total"].to_list() == [4, 6]

    def test_frame_parser_not_registered_raises(self, registry):
        schema = SchemaModel.from_dict(
            {
                "frame_parsers": [{"name": "does_not_exist"}],
                "columns": {"a": {"dtype": "Int64"}},
            }
        )
        with pytest.raises(PipelineError, match="not found in registry"):
            schema.validate(pl.DataFrame({"a": [1]}), registry)

    def test_frame_parser_execution_failure_raises(self, registry):
        decorators = ValidatorDecorator(registry)

        @decorators.frame_parser(name="explode", preserve_columns=False)
        def explode(frame: pl.LazyFrame) -> pl.LazyFrame:  # noqa: ARG001
            raise ValueError("boom")

        schema = SchemaModel.from_dict(
            {
                "frame_parsers": [{"name": "explode"}],
                "columns": {"a": {"dtype": "Int64"}},
            }
        )
        with pytest.raises(PipelineError, match="boom"):
            schema.validate(pl.DataFrame({"a": [1]}), registry)

    def test_frame_check_raises_on_failure(self, registry):
        decorators = ValidatorDecorator(registry)

        @decorators.frame_check(name="min_rows")
        def min_rows(frame: pl.LazyFrame, min_rows: int = 1) -> pl.LazyFrame:
            if frame.select(pl.len()).collect().item() < min_rows:
                raise ValueError("not enough rows")
            return frame

        schema = SchemaModel.from_dict(
            {
                "frame_checks": [{"name": "min_rows", "args": {"min_rows": 5}}],
                "columns": {"a": {"dtype": "Int64"}},
            }
        )
        with pytest.raises(PipelineError, match="not enough rows"):
            schema.validate(pl.DataFrame({"a": [1, 2]}), registry)

    def test_frame_check_passes_through_on_success(self, registry):
        decorators = ValidatorDecorator(registry)

        @decorators.frame_check(name="min_rows")
        def min_rows(frame: pl.LazyFrame, min_rows: int = 1) -> pl.LazyFrame:
            if frame.select(pl.len()).collect().item() < min_rows:
                raise ValueError("not enough rows")
            return frame

        schema = SchemaModel.from_dict(
            {
                "frame_checks": [{"name": "min_rows", "args": {"min_rows": 1}}],
                "columns": {"a": {"dtype": "Int64"}},
            }
        )
        df = pl.DataFrame({"a": [1, 2]})
        result = schema.validate(df, registry)
        assert result.data.collect()["a"].to_list() == [1, 2]

    def test_frame_check_not_registered_raises(self, registry):
        schema = SchemaModel.from_dict(
            {
                "frame_checks": [{"name": "does_not_exist"}],
                "columns": {"a": {"dtype": "Int64"}},
            }
        )
        with pytest.raises(PipelineError, match="not found in registry"):
            schema.validate(pl.DataFrame({"a": [1]}), registry)


# ---------------------------------------------------------------------------
# Nullification (on_failure='null')
# ---------------------------------------------------------------------------


class TestNullification:
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

    def test_nullified_values_are_not_coercion_failures(self, registry):
        """A value nulled by a failing check must not also be reported as a coercion failure.

        Both look identical from the __pre_null__ snapshot alone (wasn't null before
        coercion, is null now), so the report must distinguish them.
        """
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "null",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": ["10", "-1", "20"]})
        result = schema.validate(df, registry)
        assert result.report.columns["age"].coercion_failures == 0
        assert result.report.columns["age"].nullified == 1

    def test_coercion_and_check_nulls_under_streaming(self, registry):
        """#11 step 4: the streaming-engine aggregate collect in _apply_check_null must
        agree with the with_columns mutation that follows it on the same lazy graph.
        """
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "null",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": ["10", "-1", "bad", "20"]})
        result = schema.validate(df, registry)
        assert result.data.collect()["age"].to_list() == [10, None, None, 20]
        assert result.report.columns["age"].nullified == 1
        assert result.report.columns["age"].coercion_failures == 1

    def test_coercion_failures_are_reported(self, registry):
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "ignore",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": ["10", "bad", "20"]})
        result = schema.validate(df, registry)
        assert result.report.columns["age"].coercion_failures == 1
        assert "Coercion failures: 1" in result.report.summary()

    def test_coercion_failures_appear_in_errors(self, registry):
        """Coercion failures follow the same reporting path as parser/check failures."""
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "ignore",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": ["10", "bad", "20"]})
        result = schema.validate(df, registry)
        assert result.errors.filter((pl.col("column") == "age") & (pl.col("check") == "coerce"))["count"].item() == 1

    def test_coercion_failures_reduce_rows_valid(self, registry):
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "ignore",
                "columns": {"age": {"dtype": "Int64", "nullable": True}},
            }
        )
        df = pl.DataFrame({"age": ["10", "bad", "20"]})
        result = schema.validate(df, registry)
        assert result.report.rows_processed == 3
        assert result.report.rows_valid == 2

    def test_coercion_raise_is_strict_by_default(self, registry):
        """Default on_failure='raise' stops before checks ever run on the coerced garbage."""
        schema = SchemaModel.from_dict({"coerce": True, "columns": {"age": {"dtype": "Int64", "nullable": True}}})
        df = pl.DataFrame({"age": ["10", "bad", "20"]})
        with pytest.raises(PipelineError, match="Coercion failed for column 'age'"):
            schema.validate(df, registry)

    def test_non_nullable_coercion_failure_counts_once(self, registry):
        """A coercion-failed cell on a nullable=False column is null: both constraints fail.

        Both should be reported, but the row must only count as invalid once.
        """
        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "on_failure": "ignore",
                "columns": {"age": {"dtype": "Int64", "nullable": False}},
            }
        )
        df = pl.DataFrame({"age": ["10", "bad", "20"]})
        result = schema.validate(df, registry)
        assert result.report.rows_processed == 3
        assert result.report.rows_valid == 2
        assert result.errors.filter((pl.col("column") == "age") & (pl.col("check") == "coerce"))["count"].item() == 1
        assert result.errors.filter((pl.col("column") == "age") & (pl.col("check") == "not_null"))["count"].item() == 1

    def test_coercion_check_name_is_reserved(self, registry):
        """A user check named 'coerce' on a coerced column must not silently collide."""
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="coerce", tags=[])
        def fake_coerce(column: pl.Expr) -> pl.Expr:
            return column > 0

        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "coerce"}]},
                },
            }
        )
        with pytest.raises(PipelineError, match="reserved"):
            schema.validate(pl.DataFrame({"age": ["1", "2"]}), registry)

    def test_coercion_name_reserved_without_a_cast(self, registry):
        """The reservation is a schema property, not conditional on this input needing a cast."""
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="coerce", tags=[])
        def fake_coerce(column: pl.Expr) -> pl.Expr:
            return column > 0

        schema = SchemaModel.from_dict(
            {
                "coerce": True,
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "coerce"}]},
                },
            }
        )
        with pytest.raises(PipelineError, match="reserved"):
            schema.validate(pl.DataFrame({"age": [1, 2]}), registry)

    def test_coercion_name_reserved_when_disabled(self, registry):
        """The name stays reserved because downstream consumers always treat it as internal."""
        decorators = ValidatorDecorator(registry)

        @decorators.column_check(name="coerce", tags=[])
        def fake_coerce(column: pl.Expr) -> pl.Expr:
            return column > 0

        schema = SchemaModel.from_dict(
            {
                "coerce": False,
                "columns": {
                    "age": {"dtype": "Int64", "nullable": True, "checks": [{"name": "coerce"}]},
                },
            }
        )
        with pytest.raises(PipelineError, match="reserved"):
            schema.validate(pl.DataFrame({"age": [1, 2]}), registry)


# ---------------------------------------------------------------------------
# Error report modes
# ---------------------------------------------------------------------------


class TestErrorReporting:
    def test_summary_mode_count_columns(self, registry):
        schema = SchemaModel.from_dict(
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
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
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
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
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
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
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
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
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
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
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
                        "on_failure": "ignore",
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
    def test_summary_with_failures(self, registry):
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
        df = pl.DataFrame({"age": [10, -1, 5]})
        result = schema.validate(df, registry)
        text = result.report.summary()
        assert "Validation Report" in text
        assert "Check failures" in text
        assert "Nullified: 1" in text
        assert "Final nulls: 1" in text

    def test_summary_all_valid(self, registry):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": True}}})
        df = pl.DataFrame({"age": [1, 2, 3]})
        result = schema.validate(df, registry)
        text = result.report.summary()
        assert "3/3 valid" in text

    def test_empty_frame_summary_avoids_zero_division(self, registry):
        schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": True}}})
        df = pl.DataFrame({"age": []}, schema={"age": pl.Int64})
        result = schema.validate(df, registry)
        text = result.report.summary()
        assert "0/0 valid (0.0%)" in text


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

    def test_column_raise_overrides_schema_null(self, registry):
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

    def test_check_raise_on_failure(self, registry):
        """on_failure=raise + a failing check raises PipelineError, not just a recorded error."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "raise",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": [1, -5, 3]})
        with pytest.raises(PipelineError, match="Check failed for column 'age'"):
            schema.validate(df, registry)

    def test_not_null_precedes_check_raise(self, registry):
        """The not-null raise wins when a column fails both, matching pipeline order.

        Both raises carry phase='column_checks' and sit next to each other in the
        post-collect raise pass, so a reordering there would swap which message the
        caller sees without failing anything else.
        """
        schema = SchemaModel.from_dict(
            {
                "on_failure": "raise",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": False,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": [None, -5, 3]}, schema={"age": pl.Int64})
        with pytest.raises(PipelineError, match="has nullable=False but contains null values"):
            schema.validate(df, registry)

    def test_check_ignore_does_not_raise(self, registry):
        """on_failure=ignore records the failure but does not raise or nullify."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "ignore",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": [1, -5, 3]})
        result = schema.validate(df, registry)
        assert result.data.collect()["age"].to_list() == [1, -5, 3]
        assert result.errors["count"].item() == 1

    def test_check_null_nullifies_failing_values(self, registry):
        """on_failure=null nulls out values that failed a check, keeps passing values."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "null",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": [10, -1, 5, -3]})
        result = schema.validate(df, registry)
        assert result.data.collect()["age"].to_list() == [10, None, 5, None]

    def test_check_null_reports_original_value(self, registry):
        """The error report reflects the original failing value, not the post-nullification null."""
        schema = SchemaModel.from_dict(
            {
                "on_failure": "null",
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    }
                },
            }
        )
        df = pl.DataFrame({"age": [10, -1]})
        result = schema.validate(df, registry, error_report_config=ErrorReportConfig(mode="cells"))
        assert result.errors["value"].to_list() == ["-1"]

    def test_check_null_nullifies_own_column_only(self, registry):
        """Nullifying a failing on_failure=null column does not affect an unrelated ignore column."""
        schema = SchemaModel.from_dict(
            {
                "columns": {
                    "age": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "null",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    },
                    "score": {
                        "dtype": "Int64",
                        "nullable": True,
                        "on_failure": "ignore",
                        "checks": [{"name": "min_value", "args": {"min": 0}}],
                    },
                },
            }
        )
        df = pl.DataFrame({"age": [-1, 5], "score": [-1, 5]})
        result = schema.validate(df, registry)
        data = result.data.collect()
        assert data["age"].to_list() == [None, 5]
        assert data["score"].to_list() == [-1, 5]


def test_frame_parser_cannot_remove_required_column(registry):
    decorators = ValidatorDecorator(registry)

    @decorators.frame_parser(name="drop_required", preserve_columns=False)
    def drop_required(frame: pl.LazyFrame) -> pl.LazyFrame:
        return frame.drop("name")

    schema = SchemaModel.from_dict(
        {
            "frame_parsers": [{"name": "drop_required"}],
            "columns": {
                "id": {"dtype": "Int64"},
                "name": {"dtype": "Utf8"},
            },
        }
    )

    with pytest.raises(PipelineError, match=r"removed required columns: \['name'\]"):
        schema.validate(pl.DataFrame({"id": [1], "name": ["Alice"]}), registry)


@pytest.mark.parametrize("mode", ["summary", "rows", "cells"])
def test_frame_parser_preserves_error_tracking(registry, mode):
    decorators = ValidatorDecorator(registry)

    @decorators.frame_parser(name="select_columns", preserve_columns=False)
    def select_columns(frame: pl.LazyFrame) -> pl.LazyFrame:
        assert "__row_index__" not in frame.collect_schema().names()
        return frame.select("age")

    schema = SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "frame_parsers": [{"name": "select_columns"}],
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                }
            },
        }
    )

    result = schema.validate(
        pl.DataFrame({"age": [-1, 2], "unused": ["x", "y"]}),
        registry,
        error_report_config=ErrorReportConfig(mode=mode),
    )

    assert result.report.rows_valid == 1
    if mode == "summary":
        assert result.errors["count"].item() == 1
    elif mode == "rows":
        assert result.errors["row_indices"].to_list() == [[0]]
    else:
        assert result.errors["row_index"].to_list() == [0]


def test_check_mask_index_counts_per_check(registry):
    """The `__check__{n}` counter advances per check, not per column.

    `ColumnCheckPhase` iterates `schema.columns_with_checks` and numbers the masks
    from a counter incremented inside the inner loop over a column's checks. The
    numbering therefore depends on that view preserving `schema.columns` order and
    on columns without declared checks being skipped rather than consuming an index.

    Aliases are opaque handles that nothing parses, so a shift here does not fail
    anything on its own. It surfaces later as a collision or a missed lookup, which
    is why it is pinned rather than left to the suite. Phase 1.3 rewrites this code.
    """
    check = [{"name": "min_value", "args": {"min": 0}}]
    schema = SchemaModel.from_dict(
        {
            "columns": {
                "a": {"dtype": "Int64"},
                "b": {"dtype": "Int64", "checks": check},
                "c": {"dtype": "Int64", "nullable": False},
                "d": {"dtype": "Int64", "checks": [*check, {"name": "unique"}]},
            }
        }
    )
    df = pl.DataFrame({"a": [1], "b": [1], "c": [1], "d": [1]})
    context = PipelineContext(data=df.lazy(), schema=schema, registry=registry)

    result = create_pipeline_from_schema(schema).execute(context)
    declared = {key: alias for key, alias in result.check_masks.items() if key[1] != NOT_NULL_CHECK}

    assert declared == {
        ("b", "min_value"): "__check__0",
        ("d", "min_value"): "__check__1",
        ("d", "unique"): "__check__2",
    }, "column 'a' has no declared checks and must not consume an index"


def test_parsers_apply_in_declared_order(registry):
    """A column's parsers chain in the order the schema lists them.

    `ColumnParsingPhase` folds them into one expression, `expr = parser(expr)` per
    step, so the declared order is the applied order. Pinned with a non-commutative
    pair, because a test using parsers that commute would pass either way and this
    property fails silently: a reordering produces different data, not an error.
    """

    def parsed(*names: str) -> list[str]:
        schema = SchemaModel.from_dict({"columns": {"a": {"dtype": "Utf8", "parsers": [{"name": n} for n in names]}}})
        result = schema.validate(pl.DataFrame({"a": ["MiXeD"]}), registry, lazy=False)
        return result.data["a"].to_list()

    assert parsed("lower", "upper") == ["MIXED"], "the last parser listed wins"
    assert parsed("upper", "lower") == ["mixed"]
