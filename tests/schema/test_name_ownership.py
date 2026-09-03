"""Tests for column name ownership.

Every name a schema accepts, canonical or synonym, must be claimed by exactly one
column. A schema whose names overlap cannot be resolved unambiguously, so it is a
schema error and is rejected when the schema is built, before any data is
involved. See #86.
"""

import pytest

from nyctea import SchemaModel


def test_distinct_synonyms_are_accepted():
    schema = SchemaModel.from_dict(
        {
            "columns": {
                "age": {"dtype": "Int64", "synonyms": ["Age", "AGE"]},
                "name": {"dtype": "Utf8", "synonyms": ["Name"]},
            }
        }
    )

    assert schema.accepted_names == frozenset({"age", "Age", "AGE", "name", "Name"})


def test_two_columns_cannot_claim_the_same_synonym():
    with pytest.raises(ValueError, match=r"'x' is claimed by more than one column: 'age', 'years'"):
        SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64", "synonyms": ["x"]},
                    "years": {"dtype": "Int64", "synonyms": ["x"]},
                }
            }
        )


def test_a_synonym_cannot_shadow_another_columns_canonical_name():
    with pytest.raises(ValueError, match=r"'age' is claimed by more than one column: 'age', 'years'"):
        SchemaModel.from_dict(
            {
                "columns": {
                    "age": {"dtype": "Int64"},
                    "years": {"dtype": "Int64", "synonyms": ["age"]},
                }
            }
        )


def test_a_column_cannot_list_its_own_canonical_name_as_a_synonym():
    with pytest.raises(ValueError, match=r"'age' is declared more than once by column 'age'"):
        SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["age"]}}})


def test_a_column_cannot_repeat_a_synonym():
    with pytest.raises(ValueError, match=r"'Age' is declared more than once by column 'age'"):
        SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age", "Age"]}}})


def test_every_conflict_is_reported_at_once():
    """One round trip per fix, not one per conflict."""
    with pytest.raises(ValueError, match="exactly one owner") as exc:
        SchemaModel.from_dict(
            {
                "columns": {
                    "a": {"dtype": "Int64", "synonyms": ["x"]},
                    "b": {"dtype": "Int64", "synonyms": ["x", "a"]},
                }
            }
        )

    message = str(exc.value)
    assert "'a' is claimed by more than one column: 'a', 'b'" in message
    assert "'x' is claimed by more than one column: 'a', 'b'" in message


def test_ownership_is_case_sensitive():
    """Exact matching is the default, so names differing only in case are distinct owners."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}, "Age": {"dtype": "Int64"}}})

    assert schema.canonical_by_accepted_name["age"] == "age"
    assert schema.canonical_by_accepted_name["Age"] == "Age"
