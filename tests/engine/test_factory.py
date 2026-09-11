"""Tests for create_pipeline_from_schema's phase selection and ordering."""

import polars as pl
import pytest

from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.phases import CoercionPhase, ColumnCheckPhase, ColumnResolutionPhase, NotNullPhase
from nyctea.engine.pipeline import ValidationPipeline
from nyctea.exceptions import PipelineError
from nyctea.schema.model import SchemaModel
from nyctea.validators.decorators import checker
from nyctea.validators.registry import Registry


@pytest.fixture
def registry():
    return Registry()


def _phase_names(schema_dict):
    schema = SchemaModel.from_dict(schema_dict)
    pipeline = create_pipeline_from_schema(schema)
    return [phase.name for phase in pipeline.phases]


def test_frame_phases_absent_when_undeclared():
    names = _phase_names({"columns": {"a": {"dtype": "Int64"}}})
    assert "frame_parsing" not in names
    assert "frame_checks" not in names


def test_frame_parsing_precedes_column_parsing():
    names = _phase_names(
        {
            "frame_parsers": [{"name": "whatever"}],
            "columns": {"a": {"dtype": "Int64", "parsers": [{"name": "strip"}]}},
        }
    )
    assert names.index("frame_parsing") < names.index("column_parsing")


def test_frame_check_phase_ordering():
    """The frame check phase is included, after coercion and before nullability."""
    names = _phase_names(
        {
            "frame_checks": [{"name": "whatever"}],
            "columns": {"a": {"dtype": "Int64", "nullable": False}},
        }
    )
    assert names.index("coercion") < names.index("frame_checks") < names.index("not_null")


def test_not_null_is_the_last_phase():
    """Anything before it can introduce a null, so anywhere else answers a different question."""
    names = _phase_names(
        {
            "frame_parsers": [{"name": "whatever"}],
            "frame_checks": [{"name": "whatever"}],
            "columns": {
                "a": {
                    "dtype": "Int64",
                    "nullable": False,
                    "parsers": [{"name": "to_int"}],
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                }
            },
        }
    )
    assert names[-1] == "not_null"


def test_resolution_is_the_first_phase():
    """Nothing can act on a column before the schema knows which physical column it is."""
    names = _phase_names(
        {
            "frame_parsers": [{"name": "whatever"}],
            "columns": {"a": {"dtype": "Int64", "nullable": False}},
        }
    )
    assert names[0] == "column_resolution"


def test_nullability_is_not_the_check_phase():
    """A non-nullable column with no declared checks needs nullability, not the check phase."""
    names = _phase_names({"columns": {"a": {"dtype": "Int64", "nullable": False}}})

    assert "not_null" in names
    assert "column_checks" not in names


# ---------------------------------------------------------------------------
# Coercion, parsing, and checks are freely orderable against each other. Only
# resolution (first) and nullability (last) are fixed positions.
# ---------------------------------------------------------------------------


def test_column_checks_no_coercion_dependency():
    assert ColumnCheckPhase().dependencies == ["column_resolution"]


def test_frame_checks_no_coercion_dependency():
    from nyctea.engine.phases import FrameCheckPhase

    assert FrameCheckPhase().dependencies == ["column_resolution"]


def test_checks_before_coercion_is_valid():
    """The default factory order is coercion, then checks; the reverse must also construct."""
    pipeline = ValidationPipeline(
        phases=[
            ColumnResolutionPhase(),
            ColumnCheckPhase(),
            CoercionPhase(),
            NotNullPhase(),
        ]
    )
    assert pipeline.list_phases() == ["column_resolution", "column_checks", "coercion", "not_null"]


def test_check_before_coercion_sees_uncoerced_value(registry):
    """A check placed before coercion judges the value the input actually was, not the cast result.

    Written against raw strings: `looks_like_digits` would reject every row if it ran after
    coercion turned the column into Int64, since `.str.contains` is not defined on Int64.
    """

    @checker(name="looks_like_digits", tags=[], registry=registry)
    def looks_like_digits(column: pl.Expr) -> pl.Expr:
        return column.str.contains(r"^\d+$")

    schema = SchemaModel.from_dict(
        {
            "coerce": True,
            "on_failure": "ignore",
            "columns": {"a": {"dtype": "Int64", "checks": [{"name": "looks_like_digits"}]}},
        }
    )
    context = PipelineContext(
        data=pl.DataFrame({"a": ["123", "abc"]}).lazy().with_row_index("__row_index__"),
        schema=schema,
        registry=registry,
    )
    pipeline = ValidationPipeline(
        phases=[
            ColumnResolutionPhase(),
            ColumnCheckPhase(),
            CoercionPhase(),
            NotNullPhase(),
        ]
    )

    result = pipeline.execute(context)

    alias = result.check_masks[("a", "looks_like_digits")]
    assert result.data.select(alias).collect()[alias].to_list() == [True, False]


def test_notnull_still_last_after_reordering():
    """Nullability stays pinned last regardless of how the free phases in between are ordered."""
    with pytest.raises(PipelineError, match="'not_null' is pinned last"):
        ValidationPipeline(
            phases=[
                ColumnResolutionPhase(),
                NotNullPhase(),
                ColumnCheckPhase(),
                CoercionPhase(),
            ]
        )


def test_resolution_not_first_is_rejected():
    """Resolution stays pinned first regardless of how the free phases in between are ordered.

    Every other phase reads resolved names, so moving resolution later also breaks its
    dependents' own `dependencies` check; either guard rejecting it is correct here. The pin
    check in isolation, without a dependency also catching it, is pinned generically in
    test_pipeline.py.
    """
    with pytest.raises(PipelineError):
        ValidationPipeline(
            phases=[
                ColumnCheckPhase(),
                ColumnResolutionPhase(),
                CoercionPhase(),
                NotNullPhase(),
            ]
        )
