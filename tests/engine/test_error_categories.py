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


def test_binary_values_render_as_hex(registry):
    """A Binary column's failing value is hex-encoded rather than cast to text.

    Casting assumes UTF-8, so a column holding anything else failed the whole
    report rather than rendering one value oddly. Hex applies to every Binary
    column, so a value's representation does not depend on its own bytes.
    """
    from nyctea.validators.decorators import checker

    @checker(name="is_empty", registry=registry)
    def is_empty(column: pl.Expr) -> pl.Expr:
        return column.bin.size() < 1

    schema = SchemaModel.from_dict(
        {"on_failure": "ignore", "columns": {"payload": {"dtype": "Binary", "checks": [{"name": "is_empty"}]}}}
    )
    frame = pl.DataFrame({"payload": [b"\xff\xfe\x00", b"ok"]})

    result = schema.validate(frame, registry, error_report_config=ErrorReportConfig(mode="cells"))

    assert [row["value"] for row in result.errors.to_dicts()] == ["fffe00", "6f6b"]
