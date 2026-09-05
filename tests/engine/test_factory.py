"""Tests for create_pipeline_from_schema's phase selection and ordering."""

from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.schema.model import SchemaModel


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
    """Anything before it can introduce a null, so anywhere else answers a different question.

    See `.agents/design/202609052323_phase-ordering-invariants.md` and #87.
    """
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
