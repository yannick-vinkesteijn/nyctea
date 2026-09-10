"""One realistic run through the whole package, from a CSV on disk to a report.

Every other test file pins one behaviour. This one exercises the path a user
actually takes, so that a refactor which keeps each piece correct in isolation
but wires them together wrongly still fails.
"""

import polars as pl
import pytest

from nyctea import ErrorReportConfig, Registry, SchemaModel, register_builtins
from nyctea.ingest.readers import read_csv


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
                    "nullable": True,
                    "synonyms": ["Age", "AGE"],
                    "parsers": [{"name": "strip"}, {"name": "to_int"}],
                    "checks": [{"name": "min_value", "args": {"min": 0}}],
                },
                "city": {
                    "dtype": "String",
                    "nullable": False,
                    "on_failure": "ignore",
                    "parsers": [{"name": "lower"}],
                },
                "score": {"dtype": "Float64", "nullable": True},
            },
        }
    )


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "people.csv"
    path.write_text(
        "Age,city,score\n"
        " 30 ,Amsterdam,1.5\n"  # clean
        " -1 ,Utrecht,2.5\n"  # fails the min_value check
        "notanumber,Delft,3.5\n"  # parser failure
        " 40 ,,4.5\n"  # null in a nullable=False column
        " 25 ,Rotterdam,notafloat\n"  # coercion failure
    )
    return path


def test_csv_to_report_end_to_end(schema, registry, csv_path):
    """Synonym rename, parsers, coercion, checks and the report, in one run."""
    frame = read_csv(csv_path, schema, lazy=False)
    result = schema.validate(frame, registry, error_report_config=ErrorReportConfig(mode="summary"))

    data = result.data.collect() if isinstance(result.data, pl.LazyFrame) else result.data

    # The synonym was renamed and no helper column survived.
    assert data.columns == ["age", "city", "score"]

    # Parsers ran before coercion: " 30 " stripped and parsed, "notanumber" nulled.
    assert data["age"].to_list() == [30, -1, None, 40, 25]
    assert data["city"].to_list() == ["amsterdam", "utrecht", "delft", None, "rotterdam"]
    assert data["score"].to_list() == [1.5, 2.5, 3.5, 4.5, None]

    report = result.report
    assert report.rows_processed == 5
    assert report.rows_valid == 1

    assert report.columns["age"].parse_failures == 1
    assert report.columns["age"].check_failures == 1
    assert report.columns["city"].check_failures == 1
    assert report.columns["score"].coercion_failures == 1

    failures = {(row["column"], row["check"]) for row in result.errors.to_dicts()}
    assert failures == {
        ("age", "parse"),
        ("age", "min_value"),
        ("city", "not_null"),
        ("score", "coerce"),
    }


@pytest.mark.parametrize("mode", ["summary", "rows", "cells"])
def test_every_error_mode_agrees(schema, registry, csv_path, mode):
    """The three report modes describe the same failures at different detail."""
    frame = read_csv(csv_path, schema, lazy=False)
    result = schema.validate(frame, registry, error_report_config=ErrorReportConfig(mode=mode))

    failures = {(row["column"], row["check"]) for row in result.errors.to_dicts()}
    assert failures == {
        ("age", "parse"),
        ("age", "min_value"),
        ("city", "not_null"),
        ("score", "coerce"),
    }
    assert result.report.rows_valid == 1


def test_lazy_run_stays_lazy(schema, registry, csv_path):
    """A lazy request returns an uncollected frame with the same contents."""
    frame = read_csv(csv_path, schema, lazy=True)
    result = schema.validate(frame, registry, lazy=True)

    assert isinstance(result.data, pl.LazyFrame)
    assert result.data.collect()["age"].to_list() == [30, -1, None, 40, 25]
