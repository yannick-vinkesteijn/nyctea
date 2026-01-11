"""Validation pipeline with customizable phases and strict dependency enforcement.

This module provides the core pipeline infrastructure for orchestrating
validation phases with dependency validation and observability hooks.
"""


import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import Enum
from typing import TYPE_CHECKING

from nyctea.engine.observability import PhaseMetrics
from nyctea.exceptions import PipelineError

if TYPE_CHECKING:
    from nyctea.engine.context import PipelineContext
    from nyctea.engine.observability import PipelineObserver

__all__ = [
    "PhaseType",
    "PipelinePhase",
    "ValidationPipeline",
]


class PhaseType(str, Enum):
    """Types of pipeline phases."""

    RESOLUTION = "resolution"  # Column name resolution
    TRACKING = "tracking"  # State tracking (null counts, etc.)
    PARSING = "parsing"  # Data transformations
    COERCION = "coercion"  # Type coercion
    CHECKING = "checking"  # Validation checks
    REPORTING = "reporting"  # Error reporting
    NULLIFICATION = "nullification"  # Lenient behavior
    FINALIZATION = "finalization"  # Final checks and report generation


class PipelinePhase(ABC):
    """Abstract base class for validation pipeline phases.

    Each phase represents a discrete step in the validation pipeline.
    Phases declare their dependencies and can be skipped conditionally.

    Attributes:
        name: Unique identifier for the phase.
        phase_type: Category of phase.
        dependencies: Names of phases that must run before this one.
    """

    def __init__(
        self,
        name: str,
        phase_type: PhaseType,
        dependencies: Sequence[str] | None = None,
    ) -> None:
        """Initialize pipeline phase.

        Args:
            name: Unique phase identifier.
            phase_type: Type of phase.
            dependencies: Names of phases this depends on (must run first).
        """
        self.name = name
        self.phase_type = phase_type
        self.dependencies = list(dependencies) if dependencies else []

    @abstractmethod
    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute the phase logic.

        Args:
            context: Current pipeline context.

        Returns:
            Updated pipeline context (may be same instance or new).

        Raises:
            PipelineError: If phase execution fails.
        """

    def can_skip(self, context: PipelineContext) -> bool:
        """Determine if this phase can be skipped.

        Override this to implement conditional phase execution.

        Args:
            context: Current pipeline context.

        Returns:
            True if phase can be skipped, False otherwise.
        """
        return False

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.__class__.__name__}(name='{self.name}')"


class ValidationPipeline:
    """Customizable validation pipeline with dependency enforcement.

    This class manages an ordered list of pipeline phases, validates
    dependencies, and orchestrates execution with observability hooks.

    Attributes:
        phases: Ordered list of pipeline phases.
        observers: List of pipeline observers for monitoring.
    """

    def __init__(
        self,
        phases: Sequence[PipelinePhase] | None = None,
        observers: Sequence[PipelineObserver] | None = None,
    ) -> None:
        """Initialize validation pipeline.

        Args:
            phases: Initial list of phases (dependency-validated).
            observers: Pipeline observers for monitoring.

        Raises:
            PipelineError: If phase dependencies are invalid.
        """
        self.phases: list[PipelinePhase] = list(phases) if phases else []
        self.observers: list[PipelineObserver] = list(observers) if observers else []
        self._locked = False

        # Validate dependencies on initialization
        if self.phases:
            self._validate_dependencies()

    def add_phase(
        self,
        phase: PipelinePhase,
        *,
        after: str | None = None,
        before: str | None = None,
    ) -> None:
        """Add a phase to the pipeline.

        Args:
            phase: Phase to add.
            after: Insert after this phase name (optional).
            before: Insert before this phase name (optional).

        Raises:
            PipelineError: If pipeline is locked or insertion violates dependencies.
            ValueError: If both after and before are specified, or neither is specified.
        """
        if self._locked:
            raise PipelineError(
                "Cannot modify pipeline after validation has started",
                phase=phase.name,
                pipeline_state="locked",
            )

        # Determine insertion point
        if after is not None and before is not None:
            raise ValueError("Cannot specify both 'after' and 'before'")

        if after is None and before is None:
            # Append to end
            self.phases.append(phase)
        elif after is not None:
            # Insert after specified phase
            try:
                idx = self._find_phase_index(after)
                self.phases.insert(idx + 1, phase)
            except KeyError as e:
                raise PipelineError(
                    f"Cannot insert phase '{phase.name}' after '{after}': "
                    f"phase '{after}' not found",
                    phase=phase.name,
                ) from e
        else:
            # Insert before specified phase
            try:
                idx = self._find_phase_index(before)
                self.phases.insert(idx, phase)
            except KeyError as e:
                raise PipelineError(
                    f"Cannot insert phase '{phase.name}' before '{before}': "
                    f"phase '{before}' not found",
                    phase=phase.name,
                ) from e

        # Validate dependencies after insertion
        try:
            self._validate_dependencies()
        except PipelineError:
            # Rollback insertion on validation failure
            self.phases.remove(phase)
            raise

    def remove_phase(self, name: str) -> None:
        """Remove a phase from the pipeline.

        Args:
            name: Name of phase to remove.

        Raises:
            PipelineError: If pipeline is locked or phase is required by others.
            KeyError: If no phase with that name exists.
        """
        if self._locked:
            raise PipelineError(
                "Cannot modify pipeline after validation has started",
                phase=name,
                pipeline_state="locked",
            )

        # Check if any other phase depends on this one
        for phase in self.phases:
            if name in phase.dependencies:
                raise PipelineError(
                    f"Cannot remove phase '{name}': required by '{phase.name}'",
                    phase=name,
                )

        # Find and remove phase
        idx = self._find_phase_index(name)
        self.phases.pop(idx)

    def _find_phase_index(self, name: str) -> int:
        """Find index of phase by name.

        Args:
            name: Phase name to find.

        Returns:
            Index of phase in list.

        Raises:
            KeyError: If phase not found.
        """
        for i, phase in enumerate(self.phases):
            if phase.name == name:
                return i
        raise KeyError(f"Phase '{name}' not found in pipeline")

    def _validate_dependencies(self) -> None:
        """Validate that all phase dependencies are satisfied.

        Raises:
            PipelineError: If dependencies are not satisfied.
        """
        phase_names = {p.name for p in self.phases}

        for i, phase in enumerate(self.phases):
            # Check each dependency
            for dep in phase.dependencies:
                if dep not in phase_names:
                    raise PipelineError(
                        f"Phase '{phase.name}' depends on '{dep}', "
                        f"but '{dep}' is not in the pipeline",
                        phase=phase.name,
                    )

                # Ensure dependency comes before this phase
                dep_idx = self._find_phase_index(dep)
                if dep_idx >= i:
                    current_order = [p.name for p in self.phases]
                    raise PipelineError(
                        f"Phase '{phase.name}' at position {i} depends on '{dep}', "
                        f"but '{dep}' is at position {dep_idx}. "
                        f"Dependencies must run before dependent phases. "
                        f"Current ordering: {current_order}",
                        phase=phase.name,
                    )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute the validation pipeline.

        Args:
            context: Initial pipeline context.

        Returns:
            Final pipeline context after all phases.

        Raises:
            PipelineError: If pipeline execution fails.
        """
        # Lock pipeline to prevent modification during execution
        self._locked = True

        # Track execution timing
        start_time = time.time()

        try:
            # Notify observers: pipeline start
            for observer in self.observers:
                observer.on_pipeline_start(context)

            # Execute each phase
            for phase in self.phases:
                # Check if phase can be skipped
                if phase.can_skip(context):
                    continue

                # Notify observers: phase start
                for observer in self.observers:
                    observer.on_phase_start(phase.name, context)

                # Execute phase with timing
                phase_start = time.time()
                try:
                    context = phase.execute(context)
                except Exception as e:
                    raise PipelineError(
                        f"Phase '{phase.name}' failed: {e}",
                        phase=phase.name,
                    ) from e
                phase_duration = time.time() - phase_start

                # Collect metrics
                metrics = PhaseMetrics(
                    phase_name=phase.name,
                    duration_seconds=phase_duration,
                    rows_processed=context.data.select("__row_index__").collect().height
                    if "__row_index__" in context.data.collect_schema().names()
                    else 0,
                )

                # Notify observers: phase end
                for observer in self.observers:
                    observer.on_phase_end(phase.name, context, metrics)

            # Calculate total duration
            total_duration = time.time() - start_time

            # Notify observers: pipeline complete
            for observer in self.observers:
                observer.on_pipeline_complete(context, total_duration)

            return context

        except Exception as e:
            # Notify observers of error
            for observer in self.observers:
                observer.on_pipeline_error(context, e)
            raise
        finally:
            # Unlock pipeline after execution
            self._locked = False

    def list_phases(self) -> list[str]:
        """Get ordered list of phase names.

        Returns:
            List of phase names in execution order.
        """
        return [p.name for p in self.phases]

    def __len__(self) -> int:
        """Get number of phases in pipeline."""
        return len(self.phases)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ValidationPipeline({len(self.phases)} phases)"
