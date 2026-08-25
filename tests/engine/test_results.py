"""Tests for the duplicate result types in engine/results.py.

Not part of the public API (nyctea/__init__.py exports ValidationReport from
engine/validate.py instead), but the class is a near-identical copy with the same
bugs, so it needs its own coverage until #12 removes the duplication.
"""

from nyctea.engine.results import ColumnValidationStats, ValidationReport


def test_summary_empty_frame_does_not_divide_by_zero():
    report = ValidationReport(rows_processed=0, rows_valid=0, on_failure="raise")
    assert "0/0 valid (0.0%)" in report.summary()


def test_summary_reports_coercion_only_failures():
    report = ValidationReport(
        rows_processed=3,
        rows_valid=2,
        on_failure="ignore",
        columns={"age": ColumnValidationStats(column_name="age", coercion_failures=1)},
    )
    assert "Coercion failures: 1" in report.summary()
