"""Whole-frame transformations, before any column parser runs."""

from nyctea.engine.context import PipelineContext
from nyctea.engine.phases.common import reject_alias_collision
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError

__all__ = ["FrameParsingPhase"]


class FrameParsingPhase(PipelinePhase):
    """Apply frame-level parsers (whole-DataFrame transformations).

    Runs before column parsing, so frame parsers see the data first (they may
    add/drop rows or columns other parsers then operate on).

    Dependencies: column_resolution
    """

    def __init__(self) -> None:
        """Initialize frame parsing phase."""
        super().__init__(
            name="frame_parsing",
            phase_type=PhaseType.PARSING,
            dependencies=["column_resolution"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply frame parsers in schema-declared order.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with the frame parsers applied.

        Raises:
            PipelineError: If a frame parser is unregistered or fails.
        """
        registry = context.registry
        input_columns = context.get_column_names()
        lf = context.data.drop("__row_index__") if "__row_index__" in input_columns else context.data

        for parser_spec in context.schema.frame_parsers:
            try:
                parser = registry.frame_parsers.get(parser_spec.name)
            except KeyError as e:
                raise PipelineError(
                    f"Frame parser '{parser_spec.name}' not found in registry. "
                    f"Available: {registry.frame_parsers.list_names()}",
                    phase=self.name,
                ) from e

            try:
                lf = parser(lf, **parser_spec.args)
            except Exception as e:
                raise PipelineError(
                    f"Frame parser '{parser_spec.name}' failed: {e}",
                    phase=self.name,
                ) from e

        output_columns = set(lf.collect_schema().names())
        missing_required = [name for name in context.schema.required_columns if name not in output_columns]
        if missing_required:
            raise PipelineError(
                f"Frame parsers removed required columns: {missing_required}",
                phase=self.name,
            )

        reject_alias_collision(
            "__row_index__",
            output_columns | context.schema.accepted_names,
            self.name,
            "row tracking after frame parsing",
        )
        context.data = lf.with_row_index("__row_index__")
        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if the schema defines no frame parsers.

        Args:
            context: Pipeline context.

        Returns:
            True if no frame parsers are defined.
        """
        return not context.schema.frame_parsers
