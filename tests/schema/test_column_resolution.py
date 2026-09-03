"""Tests for SchemaModel.resolve_columns.

Resolution is pure set work over the schema's cached name index: intersect the
physical names with the accepted names, reverse-map to canonical, group to find
ambiguity, difference against required. Nothing about the schema is recomputed
per call. See #86.
"""

import pytest

from nyctea import SchemaModel


@pytest.fixture
def schema():
    return SchemaModel.from_dict(
        {
            "columns": {
                "age": {"dtype": "Int64", "synonyms": ["Age", "AGE"]},
                "name": {"dtype": "Utf8"},
                "note": {"dtype": "Utf8", "required": False},
            }
        }
    )


def test_renames_only_where_physical_differs_from_canonical(schema):
    resolution = schema.resolve_columns(["Age", "name"])

    assert resolution.is_valid
    assert dict(resolution.rename) == {"Age": "age"}, "'name' already canonical, so not renamed"


def test_resolution_is_independent_of_column_order(schema):
    forward = schema.resolve_columns(["Age", "name", "note"])
    reverse = schema.resolve_columns(["note", "name", "Age"])

    assert dict(forward.rename) == dict(reverse.rename)
    assert forward.resolved == reverse.resolved


def test_resolved_and_missing_follow_schema_order(schema):
    """Deterministic output, so error messages and callers do not depend on input order."""
    resolution = schema.resolve_columns(["note"])

    assert resolution.resolved == ("note",)
    assert resolution.missing_required == ("age", "name")


def test_absent_optional_column_is_not_missing(schema):
    resolution = schema.resolve_columns(["age", "name"])

    assert resolution.is_valid
    assert resolution.missing_required == ()


def test_two_accepted_names_for_one_column_is_ambiguous(schema):
    resolution = schema.resolve_columns(["age", "Age", "name"])

    assert not resolution.is_valid
    assert dict(resolution.ambiguous) == {"age": ("Age", "age")}


def test_ambiguous_column_is_not_renamed(schema):
    """Guessing which of several names wins would be arbitrary, so nothing is renamed."""
    resolution = schema.resolve_columns(["age", "Age", "name"])

    assert "Age" not in resolution.rename


def test_unknown_columns_are_ignored(schema):
    """Columns the schema does not declare pass through untouched."""
    resolution = schema.resolve_columns(["Age", "name", "totally_unrelated"])

    assert resolution.is_valid
    assert "totally_unrelated" not in resolution.rename
    assert "totally_unrelated" not in resolution.resolved


def test_empty_input_reports_every_required_column(schema):
    resolution = schema.resolve_columns([])

    assert not resolution.is_valid
    assert resolution.missing_required == ("age", "name")


def test_resolution_result_is_immutable(schema):
    resolution = schema.resolve_columns(["Age", "name"])

    with pytest.raises(TypeError):
        resolution.rename["x"] = "y"


def test_resolution_does_not_rebuild_the_schema_index(schema):
    """The whole point: the per-run cost is the intersection, not rebuilding the index."""
    index_before = schema.canonical_by_accepted_name
    names_before = schema.accepted_names

    schema.resolve_columns(["Age", "name"])
    schema.resolve_columns(["AGE", "name"])

    assert schema.canonical_by_accepted_name is index_before, "index rebuilt per run"
    assert schema.accepted_names is names_before, "accepted names rebuilt per run"
