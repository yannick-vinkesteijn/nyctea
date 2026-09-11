"""Cleaned column matching. Exact stays the default and stays unchanged."""

import pytest

from nyctea import SchemaModel

BASE = {"columns": {"age": {"dtype": "Int64", "nullable": True}}}


@pytest.fixture
def exact():
    return SchemaModel.from_dict(BASE)


@pytest.fixture
def cleaned():
    return SchemaModel.from_dict({**BASE, "column_matching": "cleaned"})


def test_exact_is_the_default(exact):
    """Existing behaviour is untouched unless a schema opts in."""
    assert exact.column_matching == "exact"
    assert exact.resolve_columns([" AGE "]).missing_required == ("age",)


def test_cleaned_matches_case_and_whitespace(cleaned):
    assert dict(cleaned.resolve_columns([" AGE "]).rename) == {" AGE ": "age"}


def test_exact_beats_cleaned(cleaned):
    """Ambiguity is judged at the winning level, so an exact match wins outright."""
    resolution = cleaned.resolve_columns(["age", "AGE"])

    assert resolution.ambiguous == {}
    assert resolution.rename == {}


def test_two_cleaned_matches_are_ambiguous(cleaned):
    """Never silently choose between equally plausible matches."""
    resolution = cleaned.resolve_columns(["AGE", "Age"])

    assert dict(resolution.ambiguous) == {"age": ("AGE", "Age")}
    assert resolution.rename == {}


def test_cleaned_reuses_the_exact_index(cleaned):
    """One definition of what a schema accepts, not a second matcher."""
    assert set(cleaned.canonical_by_cleaned_name.values()) <= set(cleaned.canonical_by_accepted_name.values())


def test_colliding_cleaned_names_are_rejected():
    """Two accepted names cleaning to one string would make a match a coin toss.

    The views are built eagerly, so this is caught when the schema is constructed
    rather than on the first run that happens to touch it.
    """
    with pytest.raises(ValueError, match="makes these names ambiguous"):
        SchemaModel.from_dict(
            {
                "column_matching": "cleaned",
                "columns": {"age": {"dtype": "Int64"}, "other": {"dtype": "Int64", "synonyms": ["AGE"]}},
            }
        )
