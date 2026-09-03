"""Models returned by the validation engine."""

from dataclasses import dataclass
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from nyctea.types import OnFailureBehavior

__all__ = [
    "ColumnValidationStats",
    "ErrorReportConfig",
    "ValidationReport",
    "ValidationResult",
]


class ErrorReportConfig(BaseModel):
    """Configuration for error reporting detail level."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["summary", "rows", "cells"] = Field(
        "summary",
        description=(
            "Error reporting mode:\n"
            "- 'summary': Column + check + count only (minimal)\n"
            "- 'rows': Add row indices where failures occurred\n"
            "- 'cells': Add row indices + actual values (maximum detail)"
        ),
    )
    limit: int | None = Field(
        None,
        ge=0,
        description="Maximum number of error rows to return per column+check. None = unlimited.",
    )
    include_values: bool = Field(
        True,
        description="Include actual failing values in output (only applies to 'cells' mode)",
    )


class ColumnValidationStats(BaseModel):
    """Per-column validation statistics."""

    model_config = ConfigDict(extra="forbid")

    column_name: str
    parse_failures: int = 0
    coercion_failures: int = 0
    check_failures: int = 0
    nullified: int = Field(0, description="Values set to null due to failures")
    final_null_count: int = Field(0, description="Total nulls in output")
    original_null_count: int = Field(
        0,
        description="Nulls after column resolution and before frame and column transformations",
    )


class ValidationReport(BaseModel):
    """Comprehensive validation outcome report."""

    model_config = ConfigDict(extra="forbid")

    rows_processed: int
    rows_valid: int
    on_failure: OnFailureBehavior
    columns: dict[str, ColumnValidationStats] = Field(default_factory=dict)

    def summary(self) -> str:
        """Return a human-readable summary."""
        pct = (self.rows_valid / self.rows_processed * 100) if self.rows_processed else 0.0
        lines = [
            f"Validation Report (on_failure: {self.on_failure})",
            f"Rows: {self.rows_valid}/{self.rows_processed} valid ({pct:.1f}%)",
            "",
            "Column Issues:",
        ]
        for col_name, stats in self.columns.items():
            if (
                stats.nullified > 0
                or stats.parse_failures > 0
                or stats.check_failures > 0
                or stats.coercion_failures > 0
            ):
                lines.append(f"  {col_name}:")
                if stats.parse_failures:
                    lines.append(f"    Parse failures: {stats.parse_failures}")
                if stats.coercion_failures:
                    lines.append(f"    Coercion failures: {stats.coercion_failures}")
                if stats.check_failures:
                    lines.append(f"    Check failures: {stats.check_failures}")
                if stats.nullified:
                    lines.append(f"    Nullified: {stats.nullified}")
                lines.append(f"    Final nulls: {stats.final_null_count}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation run."""

    data: pl.DataFrame | pl.LazyFrame
    errors: pl.DataFrame
    report: ValidationReport
