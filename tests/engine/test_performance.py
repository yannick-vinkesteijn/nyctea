"""Ratchets on the work one `validate()` call does.

These are upper bounds, not exact counts, so an unrelated change that happens to
do less still passes. Each number is where the restructure left it, recorded so a
later change cannot quietly give it back.
"""

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
            "coerce": True,
            "columns": {
                f"c{i}": {
                    "dtype": "Int64",
                    "nullable": True,
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                }
                for i in range(5)
            },
        }
    )


@pytest.fixture
def frame():
    return pl.DataFrame({f"c{i}": list(range(-2, 8)) for i in range(5)})


def test_validate_collects_at_most_twice(schema, registry, frame, collect_calls):
    """One collect for every aggregate, one for the error report. No more."""
    schema.validate(frame, registry)

    assert len(collect_calls) <= 2


@pytest.mark.parametrize("mode", ["summary", "rows", "cells"])
def test_error_modes_add_no_collects(schema, registry, frame, collect_calls, mode):
    """A more detailed error report is a wider query, not an extra pass."""
    schema.validate(frame, registry, error_report_config=ErrorReportConfig(mode=mode))

    assert len(collect_calls) <= 2


def test_schema_resolves_at_most_four_times(schema, registry, frame, schema_resolutions):
    """Resolving a lazy plan's schema walks it, so consumers share one result.

    Was 9 before `PipelineContext.frame_schema()` cached it per frame. What is left
    is one resolution per frame the pipeline actually produces.
    """
    schema.validate(frame, registry)

    assert len(schema_resolutions) <= 4
