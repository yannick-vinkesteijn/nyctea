"""Whole-frame checks."""

from nyctea.engine.context import PipelineContext
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError

__all__ = ["FrameCheckPhase"]


class FrameCheckPhase(PipelinePhase):
    """Apply frame-level checks (whole-DataFrame validations).

    Runs after coercion so frame checks see typed data, and before column
    checks. The base class only enforces row count and column set on a
    ``FrameCheck``'s output, not order or values, so it should pass the frame
    through unchanged or raise, though nothing currently enforces the former.

    Dependencies: coercion
    """

    def __init__(self) -> None:
        """Initialize frame check phase."""
        super().__init__(
            name="frame_checks",
            phase_type=PhaseType.CHECKING,
            dependencies=["coercion"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply frame checks in schema-declared order.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with the frame checks applied.

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
                lf = check(lf, **check_spec.args)
            except Exception as e:
                raise PipelineError(
                    f"Frame check '{check_spec.name}' failed: {e}",
                    phase=self.name,
                ) from e

        context.data = lf
        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if the schema defines no frame checks.

        Args:
            context: Pipeline context.

        Returns:
            True if no frame checks are defined.
        """
        return not context.schema.frame_checks
