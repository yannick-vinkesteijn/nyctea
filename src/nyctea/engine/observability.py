"""Observability hooks for pipeline execution.

This module provides observer protocols and implementations for monitoring
pipeline execution, collecting metrics, and logging phase activity.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from nyctea.engine.context import PipelineContext

__all__ = [
    "LoggingObserver",
    "MetricsCollector",
    "PhaseMetrics",
    "PipelineObserver",
]


@dataclass
class PhaseMetrics:
    """Metrics collected during phase execution.

    Attributes:
        phase_name: Name of the phase.
        duration_seconds: Execution time in seconds.
        rows_processed: Number of rows processed.
        rows_modified: Number of rows modified (if applicable).
        errors_found: Number of errors found (if applicable).
        additional: Additional phase-specific metrics.
    """

    phase_name: str
    duration_seconds: float
    rows_processed: int = 0
    rows_modified: int = 0
    errors_found: int = 0
    additional: dict[str, any] = field(default_factory=dict)


class PipelineObserver(Protocol):
    """Protocol for observing pipeline execution.

    Observers implement this protocol to receive notifications about
    pipeline and phase lifecycle events.
    """

    def on_pipeline_start(self, context: PipelineContext) -> None:
        """Called when pipeline starts execution.

        Args:
            context: Pipeline context at start.
        """
        ...

    def on_phase_start(self, phase_name: str, context: PipelineContext) -> None:
        """Called before a phase executes.

        Args:
            phase_name: Name of the phase about to execute.
            context: Current pipeline context.
        """
        ...

    def on_phase_end(
        self,
        phase_name: str,
        context: PipelineContext,
        metrics: PhaseMetrics,
    ) -> None:
        """Called after a phase completes.

        Args:
            phase_name: Name of the phase that completed.
            context: Current pipeline context (potentially modified).
            metrics: Metrics collected during phase execution.
        """
        ...

    def on_pipeline_complete(
        self,
        context: PipelineContext,
        total_duration: float,
    ) -> None:
        """Called when pipeline completes successfully.

        Args:
            context: Final pipeline context.
            total_duration: Total pipeline execution time in seconds.
        """
        ...

    def on_pipeline_error(
        self,
        context: PipelineContext,
        error: Exception,
    ) -> None:
        """Called when pipeline encounters an error.

        Args:
            context: Pipeline context at time of error.
            error: The exception that occurred.
        """
        ...


class LoggingObserver:
    """Observer that logs pipeline execution to Python logger.

    This observer provides structured logging of pipeline and phase
    lifecycle events for debugging and monitoring.

    Attributes:
        logger: Python logger to use.
        log_level: Log level for phase events.
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        log_level: int = logging.INFO,
    ) -> None:
        """Initialize logging observer.

        Args:
            logger: Logger instance (defaults to nyctea.engine logger).
            log_level: Log level for phase events.
        """
        self.logger = logger or logging.getLogger("nyctea.engine")
        self.log_level = log_level

    def on_pipeline_start(self, context: PipelineContext) -> None:
        """Log pipeline start."""
        self.logger.log(
            self.log_level,
            "Pipeline starting: %d columns, coerce_strategy=%s",
            len(context.schema.columns),
            context.coerce_strategy,
        )

    def on_phase_start(self, phase_name: str, context: PipelineContext) -> None:
        """Log phase start."""
        self.logger.log(
            self.log_level,
            "Phase starting: %s",
            phase_name,
        )

    def on_phase_end(
        self,
        phase_name: str,
        context: PipelineContext,
        metrics: PhaseMetrics,
    ) -> None:
        """Log phase completion with metrics."""
        self.logger.log(
            self.log_level,
            "Phase completed: %s (%.3fs, %d rows)",
            phase_name,
            metrics.duration_seconds,
            metrics.rows_processed,
        )

    def on_pipeline_complete(
        self,
        context: PipelineContext,
        total_duration: float,
    ) -> None:
        """Log pipeline completion."""
        self.logger.log(
            self.log_level,
            "Pipeline completed: %.3fs total",
            total_duration,
        )

    def on_pipeline_error(
        self,
        context: PipelineContext,
        error: Exception,
    ) -> None:
        """Log pipeline error."""
        self.logger.error(
            "Pipeline failed: %s",
            error,
            exc_info=True,
        )


class MetricsCollector:
    """Observer that collects metrics from pipeline execution.

    This observer accumulates phase metrics for performance analysis
    and monitoring.

    Attributes:
        phase_metrics: List of metrics collected from each phase.
        total_duration: Total pipeline execution time.
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self.phase_metrics: list[PhaseMetrics] = []
        self.total_duration: float = 0.0
        self._pipeline_start_time: float = 0.0

    def on_pipeline_start(self, context: PipelineContext) -> None:
        """Record pipeline start time."""
        self._pipeline_start_time = time.time()
        self.phase_metrics = []

    def on_phase_start(self, phase_name: str, context: PipelineContext) -> None:
        """No-op for phase start."""

    def on_phase_end(
        self,
        phase_name: str,
        context: PipelineContext,
        metrics: PhaseMetrics,
    ) -> None:
        """Collect phase metrics."""
        self.phase_metrics.append(metrics)

    def on_pipeline_complete(
        self,
        context: PipelineContext,
        total_duration: float,
    ) -> None:
        """Record total duration."""
        self.total_duration = total_duration

    def on_pipeline_error(
        self,
        context: PipelineContext,
        error: Exception,
    ) -> None:
        """Record duration at error time."""
        self.total_duration = time.time() - self._pipeline_start_time

    def get_summary(self) -> dict[str, any]:
        """Get metrics summary.

        Returns:
            Dictionary with pipeline metrics summary.
        """
        return {
            "total_duration": self.total_duration,
            "num_phases": len(self.phase_metrics),
            "phases": [
                {
                    "name": m.phase_name,
                    "duration": m.duration_seconds,
                    "rows_processed": m.rows_processed,
                    "errors_found": m.errors_found,
                }
                for m in self.phase_metrics
            ],
        }
