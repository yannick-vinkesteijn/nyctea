"""Validation pipeline with customizable phases and strict dependency enforcement."""

import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

import polars as pl

from nyctea.engine.context import PipelineContext
from nyctea.engine.observability import PhaseMetrics, PipelineObserver
from nyctea.exceptions import PipelineError, ValidationError

__all__ = [
    "PhaseType",
    "PipelinePhase",
    "ValidationPipeline",
]


class PhaseType(StrEnum):
    """Types of pipeline phases."""

    RESOLUTION = "resolution"
    TRACKING = "tracking"
    PARSING = "parsing"
    COERCION = "coercion"
    CHECKING = "checking"
    REPORTING = "reporting"
    NULLIFICATION = "nullification"
    FINALIZATION = "finalization"


class PipelinePhase(ABC):
    """Abstract base class for validation pipeline phases.

    Attributes:
        name: Unique identifier for the phase.
        phase_type: Category of phase.
        dependencies: Names of phases that must run before this one.
        pinned: `"first"`, `"last"`, or `None`. A structural position, independent
            of `dependencies`: most phases mean the same thing wherever they run
            relative to each other, but a phase whose answer depends on position
            itself (nullability answers "did the input have nulls" versus "does
            the output have nulls" depending on where it runs) needs to be fixed
            in the pipeline rather than merely ordered against named phases.
    """

    def __init__(
        self,
        name: str,
        phase_type: PhaseType,
        dependencies: Sequence[str] | None = None,
        pinned: Literal["first", "last"] | None = None,
    ) -> None:
        """Initialize pipeline phase.

        Args:
            name: Unique phase identifier.
            phase_type: Type of phase.
            dependencies: Names of phases this depends on (must run first).
            pinned: `"first"` or `"last"` to fix this phase's position in any
                pipeline it appears in, regardless of `dependencies`.

        Raises:
            PipelineError: If `pinned` is not `"first"`, `"last"`, or `None`.
        """
        if pinned is not None and pinned not in ("first", "last"):
            raise PipelineError(
                f"Phase '{name}' has pinned={pinned!r}, but pinned must be 'first', 'last', or None.",
                phase=name,
            )
        self.name = name
        self.phase_type = phase_type
        self.dependencies = list(dependencies) if dependencies else []
        self.pinned = pinned

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

    def can_change_row_count(self, context: PipelineContext) -> bool:
        """Whether execution may change the number of rows.

        Args:
            context: Current pipeline context.

        Returns:
            False unless the phase overrides this row-count contract.
        """
        return False

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.__class__.__name__}(name='{self.name}')"


class ValidationPipeline:
    """Customizable validation pipeline with dependency enforcement.

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

        if after is not None and before is not None:
            raise ValueError("Cannot specify both 'after' and 'before'")

        if after is None and before is None:
            self.phases.append(phase)
        elif after is not None:
            try:
                idx = self._find_phase_index(after)
                self.phases.insert(idx + 1, phase)
            except KeyError as e:
                raise PipelineError(
                    f"Cannot insert phase '{phase.name}' after '{after}': phase '{after}' not found",
                    phase=phase.name,
                ) from e
        elif before is not None:
            try:
                idx = self._find_phase_index(before)
                self.phases.insert(idx, phase)
            except KeyError as e:
                raise PipelineError(
                    f"Cannot insert phase '{phase.name}' before '{before}': phase '{before}' not found",
                    phase=phase.name,
                ) from e

        try:
            self._validate_dependencies()
        except PipelineError:
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

        for phase in self.phases:
            if name in phase.dependencies:
                raise PipelineError(
                    f"Cannot remove phase '{name}': required by '{phase.name}'",
                    phase=name,
                )

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
        """Validate that all phase dependencies are satisfied and pins hold.

        Raises:
            PipelineError: If dependencies are not satisfied, or a pinned phase is
                not at its required position.
        """
        phase_names = {p.name for p in self.phases}

        for i, phase in enumerate(self.phases):
            for dep in phase.dependencies:
                if dep not in phase_names:
                    raise PipelineError(
                        f"Phase '{phase.name}' depends on '{dep}', but '{dep}' is not in the pipeline",
                        phase=phase.name,
                    )

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

        self._validate_pins()

    def _validate_pins(self) -> None:
        """Validate that phases pinned "first"/"last" sit at that position.

        Independent of `dependencies`: a pin is a statement about the pipeline's
        shape, not about what a phase reads, so it holds even for a phase with no
        dependencies of its own (nullability declares none).

        Raises:
            PipelineError: If a phase pinned "first" is not at index 0, or a phase
                pinned "last" is not at the final index.
        """
        last_index = len(self.phases) - 1
        for i, phase in enumerate(self.phases):
            if phase.pinned == "first" and i != 0:
                raise PipelineError(
                    f"Phase '{phase.name}' is pinned first, but is at position {i} of {len(self.phases)}.",
                    phase=phase.name,
                )
            if phase.pinned == "last" and i != last_index:
                raise PipelineError(
                    f"Phase '{phase.name}' is pinned last, but is at position {i} of {len(self.phases)}.",
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
        self._locked = True
        start_time = time.time()

        try:
            for observer in self.observers:
                observer.on_pipeline_start(context)

            # Reuse the count while row cardinality is stable. A phase that may change
            # it triggers one refresh for all later phase metrics.
            row_count = self._count_rows(context) if self.observers else 0

            for phase in self.phases:
                if phase.can_skip(context):
                    continue
                refresh_row_count = self.observers and phase.can_change_row_count(context)
                context = self._execute_phase(phase, context, row_count)
                if refresh_row_count:
                    row_count = self._count_rows(context)

        except Exception as e:
            for observer in self.observers:
                observer.on_pipeline_error(context, e)
            raise
        else:
            total_duration = time.time() - start_time
            for observer in self.observers:
                observer.on_pipeline_complete(context, total_duration)
            return context
        finally:
            self._locked = False

    @staticmethod
    def _count_rows(context: PipelineContext) -> int:
        """Count the rows once, projecting no columns.

        `select(pl.len())` reads a single number. Materialising a column to take its
        height allocates the whole column for the same answer.

        Args:
            context: Pipeline context.

        Returns:
            Row count, or 0 when row tracking is not in place.
        """
        if "__row_index__" not in context.get_column_names():
            return 0
        return int(context.data.select(pl.len()).collect().item())

    def _execute_phase(self, phase: PipelinePhase, context: PipelineContext, row_count: int = 0) -> PipelineContext:
        """Run a single phase, notifying observers and collecting metrics.

        Args:
            phase: Phase to execute.
            context: Current pipeline context.
            row_count: Rows presented to this phase. Only read when observers are
                attached.

        Returns:
            Updated pipeline context.

        Raises:
            ValidationError: Propagated unchanged when a phase reports that the data
                does not match the schema's structure.
            PipelineError: If the phase's execute() fails for any other reason.
        """
        for observer in self.observers:
            observer.on_phase_start(phase.name, context)

        phase_start = time.time()
        try:
            context = phase.execute(context)
        except ValidationError:
            # A structural mismatch is the caller's data, not a broken phase. Wrapping
            # it would report a library fault for a schema the data does not satisfy.
            raise
        except Exception as e:
            raise PipelineError(
                f"Phase '{phase.name}' failed: {e}",
                phase=phase.name,
            ) from e
        phase_duration = time.time() - phase_start

        if self.observers:
            metrics = PhaseMetrics(
                phase_name=phase.name,
                duration_seconds=phase_duration,
                rows_processed=row_count,
            )
            for observer in self.observers:
                observer.on_phase_end(phase.name, context, metrics)

        return context

    def list_phases(self) -> list[str]:
        """Get ordered list of phase names.

        Returns:
            List of phase names in execution order.
        """
        return [p.name for p in self.phases]

    def copy(self) -> "ValidationPipeline":
        """Return an independent copy of this pipeline.

        Phase and observer instances are shared, since phases are stateless by
        design, but the copy's phase list is a separate list. Calling
        ``add_phase``/``remove_phase`` on the copy does not affect this pipeline.

        Returns:
            A new ``ValidationPipeline`` with the same phases and observers.
        """
        return ValidationPipeline(phases=list(self.phases), observers=list(self.observers))

    def __len__(self) -> int:
        """Get number of phases in pipeline."""
        return len(self.phases)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ValidationPipeline({len(self.phases)} phases)"
