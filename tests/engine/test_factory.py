"""Tests for create_pipeline_from_schema's phase selection and ordering."""

from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.schema.model import SchemaModel


def _phase_names(schema_dict):
    schema = SchemaModel.from_dict(schema_dict)
    pipeline = create_pipeline_from_schema(schema)
    return [phase.name for phase in pipeline.phases]


def test_no_frame_phases_when_schema_has_none():
    names = _phase_names({"columns": {"a": {"dtype": "Int64"}}})
    assert "frame_parsing" not in names
    assert "frame_checks" not in names


def test_frame_parsing_phase_included_and_ordered_before_column_parsing():
    names = _phase_names(
        {
            "frame_parsers": [{"name": "whatever"}],
            "columns": {"a": {"dtype": "Int64", "parsers": [{"name": "strip"}]}},
        }
    )
    assert names.index("frame_parsing") < names.index("column_parsing")


def test_frame_check_phase_included_and_ordered_between_coercion_and_column_checks():
    names = _phase_names(
        {
            "frame_checks": [{"name": "whatever"}],
            "columns": {"a": {"dtype": "Int64", "nullable": False}},
        }
    )
    assert names.index("coercion") < names.index("frame_checks") < names.index("column_checks")
