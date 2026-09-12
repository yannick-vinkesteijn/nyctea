"""Structural failures are told apart from business-rule failures."""

import polars as pl
import pytest

from nyctea import ErrorReportConfig, Registry, SchemaModel, register_builtins
from nyctea.engine.checks import category_of


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


@pytest.mark.parametrize(
    ("check", "expected"),
    [("coerce", "structural"), ("not_null", "structural"), ("parse", "structural"), ("min_value", "check")],
)
def test_category_of_names_the_kind(check, expected):
    assert category_of(check) == expected


@pytest.mark.parametrize("mode", ["summary", "rows", "cells"])
def test_every_mode_carries_the_category(schema, registry, mode):
    """A caller no longer has to know which check names mean 'structural'."""
    result = schema.validate(
        pl.DataFrame({"age": ["1", "-5", "x", None]}),
        registry,
        error_report_config=ErrorReportConfig(mode=mode),
    )

    by_check = {row["check"]: row["category"] for row in result.errors.to_dicts()}
    assert by_check["coerce"] == "structural"
    assert by_check["not_null"] == "structural"
    assert by_check["min_value"] == "check"


def test_empty_errors_carry_the_category(schema, registry):
    result = schema.validate(pl.DataFrame({"age": [1, 2]}), registry)

    assert "category" in result.errors.columns
    assert result.errors.height == 0
