"""Errors name the header the input actually used."""

import polars as pl
import pytest

from nyctea import ErrorReportConfig, Registry, SchemaModel, register_builtins


@pytest.fixture
def registry():
    registry = Registry()
    register_builtins(registry)
    return registry


@pytest.fixture
def schema():
    return SchemaModel.from_dict(
        {
            "on_failure": "ignore",
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": True,
                    "synonyms": ["Age"],
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                }
            },
        }
    )


@pytest.mark.parametrize("mode", ["summary", "rows", "cells"])
def test_synonym_header_is_reported(schema, registry, mode):
    """Once `Age` becomes `age`, only this mapping can name the user's own column."""
    result = schema.validate(pl.DataFrame({"Age": [1, -5]}), registry, error_report_config=ErrorReportConfig(mode=mode))

    row = result.errors.to_dicts()[0]
    assert row["column"] == "age"
    assert row["source_column"] == "Age"


def test_source_column_matches_when_not_renamed(schema, registry):
    """Without a synonym match the two names are the same, so the schema stays stable."""
    result = schema.validate(pl.DataFrame({"age": [1, -5]}), registry)

    row = result.errors.to_dicts()[0]
    assert row["column"] == row["source_column"] == "age"


def test_empty_errors_carry_the_column(schema, registry):
    result = schema.validate(pl.DataFrame({"Age": [1, 2]}), registry)

    assert "source_column" in result.errors.columns
    assert result.errors.height == 0
