"""The nullability postcondition, as its own phase.

`nullable: false` is the one constraint whose answer changes with position. Checked
early it says "did the input contain nulls"; checked last it says "does the output
contain nulls", and only the second is a contract a caller can rely on. A failing
parser or coercion can null a column after the fact.

So it is not a check among checks, and it is not part of `ColumnCheckPhase`. It is a
phase of its own, pinned last. See
`.agents/design/202609052323_phase-ordering-invariants.md` and #87.
"""

import polars as pl

from nyctea.engine.checks import NOT_NULL_CHECK
from nyctea.engine.context import PipelineContext
from nyctea.engine.phases.common import reserved_columns
from nyctea.engine.phases.notnull import build_notnull_mask_exprs
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError

__all__ = ["NotNullPhase"]


class NotNullPhase(PipelinePhase):
    """Register a not-null mask for every `nullable=False` column.

    Runs last, after anything that could introduce a null.
    """

    def __init__(self) -> None:
        """Initialize the nullability phase."""
        super().__init__(
            name="not_null",
            phase_type=PhaseType.CHECKING,
            dependencies=[],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Build and register the not-null masks.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with a not-null mask per non-nullable column.

        Raises:
            PipelineError: If a column declares a check named `not_null`, which is
                reserved for this constraint.
        """
        lf = context.data
        mask_exprs: list[pl.Expr] = []
        aliases = build_notnull_mask_exprs(
            context.schema,
            self.name,
            set(context.get_column_names()),
            reserved_columns(context),
            mask_exprs,
        )

        if mask_exprs:
            context.data = lf.with_columns(mask_exprs)
            context.internal_columns.update(e.meta.output_name() for e in mask_exprs)

        # Registered as checks so they reach the error report. Without this,
        # on_failure='ignore' would swallow the null entirely.
        check_masks = dict(context.check_masks)
        for col_name, alias in aliases.items():
            key = (col_name, NOT_NULL_CHECK)
            if key in check_masks:
                raise PipelineError(
                    f"Column '{col_name}' is nullable=False and also has a check named "
                    f"'{NOT_NULL_CHECK}'. The name is reserved for the built-in not-null "
                    f"constraint. Rename the check.",
                    phase=self.name,
                )
            check_masks[key] = alias
        context.check_masks = check_masks

        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip when no column declares `nullable: false`.

        Args:
            context: Pipeline context.

        Returns:
            True when there is nothing to enforce.
        """
        return not context.schema.non_nullable_columns
