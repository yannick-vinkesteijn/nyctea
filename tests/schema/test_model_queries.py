"""Tests for SchemaModel's schema query layer.

These are the named views consumers use instead of re-implementing a traversal
over ``schema.columns``. See #86.
"""

import copy
import dataclasses
import pickle

import pydantic
import pytest

from nyctea import SchemaModel


@pytest.fixture
def schema():
    return SchemaModel.from_dict(
        {
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": False,
                    "synonyms": ["Age", "AGE"],
                    "checks": [{"name": "positive"}],
                },
                "email": {
                    "dtype": "Utf8",
                    "nullable": True,
                    "required": False,
                    "parsers": [{"name": "strip"}],
                },
                "score": {"dtype": "Int64", "nullable": True},
            }
        }
    )


def test_required_columns_excludes_optional(schema):
    assert schema.required_columns == ("age", "score")


def test_non_nullable_columns(schema):
    assert schema.non_nullable_columns == ("age",)


def test_columns_with_parsers(schema):
    assert schema.columns_with_parsers == ("email",)


def test_columns_with_checks_excludes_generated_not_null(schema):
    """A non-nullable column with no declared checks is not a column 'with checks'."""
    assert schema.columns_with_checks == ("age",)


def test_columns_needing_check_phase_includes_non_nullable(schema):
    """The check phase must run for a non-nullable column even with no declared checks."""
    assert schema.columns_needing_check_phase == ("age",)

    non_nullable_only = SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64", "nullable": False}}})
    assert non_nullable_only.columns_with_checks == ()
    assert non_nullable_only.columns_needing_check_phase == ("a",)


def test_columns_to_coerce_respects_resolution(schema):
    assert schema.columns_to_coerce == ("age", "email", "score")


def test_columns_to_coerce_empty_when_schema_disables_coercion():
    schema = SchemaModel.from_dict({"coerce": False, "columns": {"age": {"dtype": "Int64"}}})
    assert schema.columns_to_coerce == ()


def test_columns_to_coerce_honours_a_column_level_override():
    schema = SchemaModel.from_dict(
        {
            "coerce": False,
            "columns": {"age": {"dtype": "Int64", "coerce": True}, "name": {"dtype": "Utf8"}},
        }
    )
    assert schema.columns_to_coerce == ("age",)


def test_accepted_names_covers_canonicals_and_synonyms(schema):
    assert schema.accepted_names == frozenset({"age", "Age", "AGE", "email", "score"})


def test_canonical_by_accepted_name_maps_synonyms_and_self(schema):
    index = schema.canonical_by_accepted_name

    assert index["Age"] == "age"
    assert index["AGE"] == "age"
    assert index["age"] == "age"
    assert index["score"] == "score"


def test_queries_preserve_schema_declaration_order():
    """Order is the schema's, not sorted, so callers get stable, predictable output."""
    schema = SchemaModel.from_dict(
        {
            "columns": {
                "zebra": {"dtype": "Int64", "nullable": False},
                "apple": {"dtype": "Int64", "nullable": False},
            }
        }
    )

    assert schema.required_columns == ("zebra", "apple")
    assert schema.non_nullable_columns == ("zebra", "apple")


def test_queries_are_empty_for_a_schema_with_no_matching_columns():
    schema = SchemaModel.from_dict({"columns": {"a": {"dtype": "Int64", "nullable": True}}})

    assert schema.columns_with_parsers == ()
    assert schema.columns_with_checks == ()
    assert schema.columns_needing_check_phase == ()
    assert schema.non_nullable_columns == ()


def test_schema_is_frozen():
    """The declared schema is the fixed reference the pipeline validates against.

    Every phase re-reads the *data's* columns because frame parsers legitimately
    add and drop them. If the declared schema could move too, there would be
    nothing stable to measure that drift against.
    """
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})

    with pytest.raises(pydantic.ValidationError):
        schema.coerce = False  # ty: ignore[invalid-assignment]

    with pytest.raises(pydantic.ValidationError):
        schema.columns["age"].nullable = True  # ty: ignore[invalid-assignment]


def test_query_views_cannot_be_mutated_through_their_return_value():
    """Cached views hand back read-only proxies, so a caller cannot corrupt the cache."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})

    with pytest.raises(TypeError):
        schema.canonical_by_accepted_name["oops"] = "age"  # ty: ignore[invalid-assignment]

    assert schema.canonical_by_accepted_name == {"age": "age", "Age": "age"}


# ---------------------------------------------------------------------------
# ResolvedColumn: the consumption shape
# ---------------------------------------------------------------------------


def test_resolved_column_knows_its_own_name():
    """ColumnSchema cannot answer this: the name is the key in schema.columns."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})

    assert schema.column("age").name == "age"


def test_resolved_column_inherits_schema_settings():
    schema = SchemaModel.from_dict({"coerce": False, "on_failure": "ignore", "columns": {"age": {"dtype": "Int64"}}})
    column = schema.column("age")

    assert schema.columns["age"].coerce is None, "authoring shape keeps the tri-state"
    assert column.coerce is False, "consumption shape resolves it"
    assert column.on_failure == "ignore"


def test_resolved_column_honours_its_own_overrides():
    schema = SchemaModel.from_dict(
        {
            "coerce": False,
            "on_failure": "ignore",
            "columns": {"age": {"dtype": "Int64", "coerce": True, "on_failure": "raise"}},
        }
    )
    column = schema.column("age")

    assert column.coerce is True
    assert column.on_failure == "raise"


def test_resolved_column_applies_the_non_nullable_guard():
    """A non-nullable column inheriting on_failure='null' resolves to 'raise'. See #25."""
    schema = SchemaModel.from_dict({"on_failure": "null", "columns": {"age": {"dtype": "Int64", "nullable": False}}})

    assert schema.column("age").on_failure == "raise"


def test_resolved_column_accepted_names_puts_canonical_first():
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age", "AGE"]}}})

    assert schema.column("age").accepted_names == ("age", "Age", "AGE")


def test_resolved_column_needs_check_phase_covers_the_generated_not_null():
    schema = SchemaModel.from_dict(
        {"columns": {"a": {"dtype": "Int64", "nullable": False}, "b": {"dtype": "Int64", "nullable": True}}}
    )

    assert schema.column("a").needs_check_phase is True, "non-nullable needs the phase for not-null"
    assert schema.column("b").needs_check_phase is False
    assert schema.column("a").has_checks is False, "the not-null constraint is generated, not declared"
    assert schema.column("a").has_parsers is False


def test_resolved_column_is_immutable():
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})

    with pytest.raises(dataclasses.FrozenInstanceError):
        schema.column("age").coerce = False  # ty: ignore[invalid-assignment]


def test_column_raises_for_an_unknown_name():
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})

    with pytest.raises(KeyError):
        schema.column("nope")


def test_resolve_methods_agree_with_the_resolved_view():
    """The old per-name API is kept, and now reads the same resolved values."""
    schema = SchemaModel.from_dict({"coerce": False, "columns": {"age": {"dtype": "Int64", "coerce": True}}})

    assert schema.resolve_coerce("age") == schema.column("age").coerce
    assert schema.resolve_on_failure("age") == schema.column("age").on_failure


# ---------------------------------------------------------------------------
# Built once, at construction
# ---------------------------------------------------------------------------

DERIVED_VIEWS = (
    "canonical_by_accepted_name",
    "accepted_names",
    "resolved_columns",
    "required_columns",
    "non_nullable_columns",
    "columns_with_parsers",
    "columns_with_checks",
    "columns_needing_check_phase",
    "columns_to_coerce",
)


def test_every_derived_view_is_built_at_construction():
    """A constructed schema is complete: nothing is deferred to first use."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})

    deferred = [view for view in DERIVED_VIEWS if view not in schema.__dict__]

    assert deferred == [], f"computed lazily instead of at construction: {deferred}"


def test_derived_views_are_never_rebuilt():
    """Reading a view repeatedly returns the same object, so runs never recompute it."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})

    first = {view: id(getattr(schema, view)) for view in DERIVED_VIEWS}
    for _ in range(10):
        schema.resolve_columns(["Age"])
    second = {view: id(getattr(schema, view)) for view in DERIVED_VIEWS}

    assert first == second


def test_indexes_are_built_only_after_ownership_is_validated():
    """An invalid schema must fail on the conflict, not on a half-built index."""
    with pytest.raises(ValueError, match="exactly one owner"):
        SchemaModel.from_dict(
            {
                "columns": {
                    "a": {"dtype": "Int64", "synonyms": ["x"]},
                    "b": {"dtype": "Int64", "synonyms": ["x"]},
                }
            }
        )


def test_schema_survives_copying_and_pickling():
    """Derived views hold read-only mappings, so they are rebuilt rather than copied.

    Matters for multiprocessing: a schema handed to a worker process must
    survive the round trip.
    """
    schema = SchemaModel.from_dict({"coerce": False, "columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})

    unpickled = pickle.loads(pickle.dumps(schema))  # noqa: S301

    for clone in (copy.deepcopy(schema), unpickled, schema.model_copy()):
        assert dict(clone.canonical_by_accepted_name) == dict(schema.canonical_by_accepted_name)
        assert clone.required_columns == schema.required_columns
        assert clone.columns_to_coerce == schema.columns_to_coerce
        deferred = [view for view in DERIVED_VIEWS if view not in clone.__dict__]
        assert deferred == [], f"clone did not rebuild: {deferred}"


def test_a_deep_copy_is_independent_and_still_frozen():
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    clone = copy.deepcopy(schema)

    assert clone is not schema
    with pytest.raises(pydantic.ValidationError):
        clone.coerce = False  # ty: ignore[invalid-assignment]
