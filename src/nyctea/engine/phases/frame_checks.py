"""Whole-frame checks."""

from nyctea.engine.context import PipelineContext
from nyctea.engine.phase_names import COLUMN_RESOLUTION_PHASE, FRAME_CHECKS_PHASE
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError

__all__ = ["FrameCheckPhase"]


class FrameCheckPhase(PipelinePhase):
    """Apply frame-level checks (whole-DataFrame validations).

    Depends only on resolved names, not on coercion: a frame check is freely
    orderable against coercion, column parsing, and frame parsing, since it judges
    whatever the frame looks like when it runs rather than assuming a particular
    dtype.

    A check judges the frame and raises, so whatever it returns is discarded. That
    makes it structurally unable to change the data, which is cheaper and more
    certain than comparing its output against its input would be.
    """

    def __init__(self) -> None:
        """Initialize frame check phase."""
        super().__init__(
            name=FRAME_CHECKS_PHASE,
            phase_type=PhaseType.CHECKING,
            dependencies=[COLUMN_RESOLUTION_PHASE],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply frame checks in schema-declared order.

        Args:
            context: Pipeline context.

        Returns:
            The context unchanged. A check judges the data, it does not transform it.

        Raises:
            PipelineError: If a frame check is unregistered or fails.
        """
        registry = context.registry
        lf = context.data

        for check_spec in context.schema.frame_checks:
            try:
                check = registry.frame_checks.get(check_spec.name)
            except KeyError as e:
                raise PipelineError(
                    f"Frame check '{check_spec.name}' not found in registry. "
                    f"Available: {registry.frame_checks.list_names()}",
                    phase=self.name,
                ) from e

            try:
                check(lf, **check_spec.args)
            except Exception as e:
                raise PipelineError(
                    f"Frame check '{check_spec.name}' failed: {e}",
                    phase=self.name,
                ) from e

        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if the schema defines no frame checks.

        Args:
            context: Pipeline context.

        Returns:
            True if no frame checks are defined.
        """
        return not context.schema.frame_checks
