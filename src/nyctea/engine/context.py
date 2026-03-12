"""Pipeline context for passing state through validation phases.

This module defines the PipelineContext dataclass, which serves as a shared
state container passed through all pipeline phases during validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from nyctea.engine.validate import ErrorReportConfig, ValidationReport
    from nyctea.plugins.registry import Registry
    from nyctea.schema.model import SchemaModel

__all__ = ["PipelineContext"]


@dataclass
class PipelineContext:
    """Shared state container for validation pipeline execution.

    This dataclass is passed through all pipeline phases, accumulating state
    and intermediate results as validation progresses.

    Attributes:
        data: The DataFrame/LazyFrame being validated (mutated by phases).
        schema: The schema definition.
        registry: Plugin registry for lookups.
        coerce_strategy: How to handle type coercion failures.
        error_report_config: Configuration for error reporting detail.
        original_nulls: Null counts before validation (set by NullCountingPhase).
        coercion_failures: Tracking coercion failures per column.
        check_failures: Tracking check failures per column and check name.
        nullified_counts: Counts of nullified values per column.
        errors: Error DataFrame (built by ErrorReportingPhase).
        report: Final validation report (built by ReportGenerationPhase).
        metadata: Additional phase-specific metadata.
    """

    # Input configuration
    data: pl.LazyFrame
    schema: SchemaModel
    registry: Registry
    coerce_strategy: str = "strict"  # "strict" or "null_on_failure"
    error_report_config: ErrorReportConfig | None = None

    # Tracking state (populated by phases)
    original_nulls: dict[str, int] = field(default_factory=dict)
    coercion_failures: dict[str, int] = field(default_factory=dict)
    check_failures: dict[tuple[str, str], int] = field(default_factory=dict)  # (col, check) -> count
    nullified_counts: dict[str, int] = field(default_factory=dict)

    # Output (built by phases)
    errors: pl.DataFrame | None = None
    report: ValidationReport | None = None

    # Phase metadata (arbitrary additional data)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_column_names(self) -> list[str]:
        """Get current column names from data."""
        return self.data.collect_schema().names()

    def set_metadata(self, key: str, value: Any) -> None:
        """Set phase-specific metadata.

        Args:
            key: Metadata key.
            value: Metadata value.
        """
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get phase-specific metadata.

        Args:
            key: Metadata key.
            default: Default value if key not found.

        Returns:
            Metadata value or default.
        """
        return self.metadata.get(key, default)
