"""Per-column checks, and the not-null constraint they carry."""

import polars as pl

from nyctea.engine.checks import COERCION_CHECK, NOT_NULL_CHECK, PARSING_CHECK
from nyctea.engine.context import PipelineContext
from nyctea.engine.phases.common import reject_alias_collision, reserved_columns
from nyctea.engine.phases.notnull import build_notnull_mask_exprs
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError
from nyctea.schema.model import Check
from nyctea.validators.registry import Registry

__all__ = ["ColumnCheckPhase"]


class ColumnCheckPhase(PipelinePhase):
    """Apply column checks (validations).

    This phase applies all column-level checks defined in the schema,
    collecting validation errors for the error report.

    Dependencies: coercion (checks run on typed data)
    """

    def __init__(self) -> None:
        """Initialize column check phase."""
        super().__init__(
            name="column_checks",
            phase_type=PhaseType.CHECKING,
            dependencies=["coercion"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply column checks.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with check failure counts.

        Raises:
            PipelineError: If check execution fails.
        """
        schema = context.schema
        registry = context.registry
        lf = context.data
        current_columns = set(context.get_column_names())
        occupied_columns = reserved_columns(context)

        # Build boolean mask columns for each check (True = passed)
        # No collect here — downstream phases use these masks lazily
        mask_exprs: list[pl.Expr] = []
        # Preserve entries earlier phases (e.g. CoercionPhase) already registered.
        check_masks: dict[tuple[str, str], str] = dict(context.check_masks)
        notnull_aliases = build_notnull_mask_exprs(
            schema,
            self.name,
            current_columns,
            occupied_columns,
            mask_exprs,
        )
        # Independent of check_masks' size, so seeded coercion entries don't shift aliases.
        check_index = 0

        for col_name in schema.columns_with_checks:
            if col_name not in current_columns:
                continue
            for check_spec in schema.column(col_name).checks:
                self._reject_reserved_or_duplicate_check(check_masks, col_name, check_spec.name)
                check_expr = self._resolve_check_expr(registry, col_name, check_spec)

                # Index, not "{col}__{check}": the latter is ambiguous, since a column named
                # 'a__b' with check 'c' and a column 'a' with check 'b__c' both produce
                # '__check__a__b__c'. Nothing parses these aliases; they are opaque handles.
                alias = f"__check__{check_index}"
                check_index += 1
                reject_alias_collision(
                    alias,
                    occupied_columns,
                    self.name,
                    f"the mask for check '{check_spec.name}' on column '{col_name}'",
                )
                mask_exprs.append(check_expr.alias(alias))
                check_masks[(col_name, check_spec.name)] = alias

        if mask_exprs:
            context.data = lf.with_columns(mask_exprs)
            context.internal_columns.update(e.meta.output_name() for e in mask_exprs)

        # Register the not-null masks as checks so they appear in the error report.
        # Without this, on_failure='ignore' would swallow the null entirely.
        for col_name, alias in notnull_aliases.items():
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

    def _reject_reserved_or_duplicate_check(
        self,
        check_masks: dict[tuple[str, str], str],
        col_name: str,
        check_name: str,
    ) -> None:
        """Reject check names reserved for internal failure tracking, or duplicate names per column.

        Args:
            check_masks: Masks registered so far, keyed on (column, check name).
            col_name: Column the check is declared on.
            check_name: Declared name of the check.

        Raises:
            PipelineError: If the name is reserved for internal tracking, or if the
                column already has a check registered under the same name.
        """
        if check_name in {COERCION_CHECK, NOT_NULL_CHECK, PARSING_CHECK}:
            raise PipelineError(
                f"Column '{col_name}' has a check named '{check_name}'. The name is "
                "reserved for built-in failure tracking. Rename the check.",
                phase=self.name,
            )

        # check_masks is keyed on (column, check name), and so are the error report and
        # the per-column report stats. A second check with the same name on the same
        # column would overwrite the first entry, orphaning its mask: that check would be
        # dropped from both reporting and enforcement, and the run would report clean.
        if (col_name, check_name) in check_masks:
            raise PipelineError(
                f"Column '{col_name}' has more than one check named '{check_name}'. "
                f"Check names must be unique per column, because error reports and the "
                f"validation report are keyed on (column, check name). Give the checks "
                f"distinct names.",
                phase=self.name,
            )

    def _resolve_check_expr(self, registry: Registry, col_name: str, check_spec: Check) -> pl.Expr:
        """Look up a check in the registry and apply it to build its boolean mask expression.

        Args:
            registry: Registry to resolve the check name against.
            col_name: Column the check applies to.
            check_spec: Declared check name and arguments.

        Returns:
            Boolean expression that is True where the check passes.

        Raises:
            PipelineError: If the check is not registered, or applying it fails.
        """
        try:
            check = registry.column_checks.get(check_spec.name)
        except KeyError as e:
            raise PipelineError(
                f"Check '{check_spec.name}' not found in registry. Available: {registry.column_checks.list_names()}",
                phase=self.name,
            ) from e

        try:
            return check(pl.col(col_name), **(check_spec.args or {}))
        except Exception as e:
            raise PipelineError(
                f"Failed to apply check '{check_spec.name}' to column '{col_name}': {e}",
                phase=self.name,
            ) from e

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no checks are defined in schema.

        Args:
            context: Pipeline context.

        Returns:
            True if no columns have checks defined.
        """
        return not context.schema.columns_needing_check_phase
