"""Cast columns to their declared dtypes."""

import polars as pl

from nyctea.engine.checks import COERCION_CHECK
from nyctea.engine.context import PipelineContext
from nyctea.engine.phases.common import reject_alias_collision, reserved_columns
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError
from nyctea.utils import resolve_dtype

__all__ = ["CoercionPhase"]


class CoercionPhase(PipelinePhase):
    """Cast columns to their declared dtypes.

    Runs after parsing so parsers operate on raw strings, and before checks
    so checks operate on typed data. Skipped when ``schema.coerce`` is False.

    Always casts with ``strict=False``. Pre-coercion null masks
    (``__pre_null__{col}``) are added for every cast column so the validator
    can detect coercion-introduced nulls at collect time and enforce
    per-column ``on_failure`` behavior.

    Dependencies: column_resolution
    """

    def __init__(self) -> None:
        """Initialize coercion phase."""
        super().__init__(
            name="coercion",
            phase_type=PhaseType.COERCION,
            dependencies=["column_resolution"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Cast columns to their schema-declared dtypes.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with coerced columns.

        Raises:
            PipelineError: If dtype is invalid.
        """
        schema = context.schema
        lf = context.data

        current_dtypes = context.frame_schema()
        occupied_columns = reserved_columns(context)
        cast_exprs: list[pl.Expr] = []

        for col_name in schema.columns_to_coerce:
            if col_name not in current_dtypes:
                continue

            dtype = schema.column(col_name).dtype
            try:
                target = resolve_dtype(dtype)
            except ValueError as e:
                raise PipelineError(
                    f"Invalid dtype '{dtype}' for column '{col_name}': {e}",
                    phase=self.name,
                ) from e

            if current_dtypes[col_name] == target:
                continue

            cast_exprs.append(pl.col(col_name).cast(target, strict=False).alias(col_name))

        if not cast_exprs:
            return context

        # Snapshot null state before casting so coercion-introduced nulls
        # can be detected at collect time.
        cols_to_cast = [expr.meta.output_name() for expr in cast_exprs]
        for c in cols_to_cast:
            reject_alias_collision(
                f"__pre_null__{c}", occupied_columns, self.name, f"the pre-null snapshot for column '{c}'"
            )
            reject_alias_collision(
                f"__coercion_ok__{c}", occupied_columns, self.name, f"the coercion mask for column '{c}'"
            )
        pre_null_exprs = [pl.col(c).is_null().alias(f"__pre_null__{c}") for c in cols_to_cast]
        context.internal_columns.update(f"__pre_null__{c}" for c in cols_to_cast)
        context.data = lf.with_columns(pre_null_exprs).with_columns(cast_exprs)

        # True = no coercion failure; feeds check_masks like a real check.
        coercion_ok_exprs = [
            (~(pl.col(c).is_null() & ~pl.col(f"__pre_null__{c}"))).alias(f"__coercion_ok__{c}") for c in cols_to_cast
        ]
        context.data = context.data.with_columns(coercion_ok_exprs)
        context.internal_columns.update(f"__coercion_ok__{c}" for c in cols_to_cast)
        context.check_masks.update({(c, COERCION_CHECK): f"__coercion_ok__{c}" for c in cols_to_cast})

        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no column needs coercion.

        Args:
            context: Pipeline context.

        Returns:
            True if no column will be coerced.
        """
        return not context.schema.columns_to_coerce
