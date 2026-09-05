"""Match the frame's column names against the schema."""

from nyctea.engine.context import PipelineContext
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import ValidationError

__all__ = ["ColumnResolutionPhase"]


class ColumnResolutionPhase(PipelinePhase):
    """Resolve column names using synonyms.

    This phase maps physical column names to canonical schema names using
    the synonym definitions in the schema.

    Dependencies: None (always runs first)
    """

    def __init__(self) -> None:
        """Initialize column resolution phase."""
        super().__init__(
            name="column_resolution",
            phase_type=PhaseType.RESOLUTION,
            dependencies=[],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Resolve column names using schema synonyms.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with resolved column names.

        Raises:
            ValidationError: If required columns are missing or ambiguous.
        """
        schema = context.schema
        lf = context.data

        resolution = schema.resolve_columns(context.get_column_names())

        for canonical, physicals in resolution.ambiguous.items():
            raise ValidationError(
                f"Ambiguous columns for '{canonical}': {list(physicals)}. Only one canonical/synonym is allowed.",
                column=canonical,
                phase=self.name,
            )

        for canonical in resolution.missing_required:
            raise ValidationError(
                f"Required column '{canonical}' is missing. "
                f"Looked for: {sorted(schema.column(canonical).accepted_names)}",
                column=canonical,
                phase=self.name,
            )

        if resolution.rename:
            context.data = lf.rename(dict(resolution.rename))

        context.original_data = context.data
        return context
