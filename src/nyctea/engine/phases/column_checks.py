"""Per-column checks declared by the schema author."""

import polars as pl

from nyctea.engine.checks import COERCION_CHECK, NOT_NULL_CHECK, PARSING_CHECK
from nyctea.engine.context import PipelineContext
from nyctea.engine.masks import CHECK_TIME_LENGTH, MASK_LENGTH_PREFIX
from nyctea.engine.phase_names import COLUMN_CHECKS_PHASE, COLUMN_RESOLUTION_PHASE
from nyctea.engine.phases.common import reject_alias_collision, reserved_columns
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError
from nyctea.schema.model import Check
from nyctea.validators.registry import Registry

__all__ = ["ColumnCheckPhase"]


class ColumnCheckPhase(PipelinePhase):
    """Apply column checks (validations).

    This phase applies all column-level checks defined in the schema,
    collecting validation errors for the error report.

    Depends only on resolved names, not on coercion: a check is freely orderable
    against coercion, column parsing, and frame parsing, since it judges whatever
    value it is handed rather than assuming a particular dtype.
    """

    def __init__(self) -> None:
        """Initialize column check phase."""
        super().__init__(
            name=COLUMN_CHECKS_PHASE,
            phase_type=PhaseType.CHECKING,
            dependencies=[COLUMN_RESOLUTION_PHASE],
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
                    col_name,
                )
                mask_exprs.append(check_expr.alias(alias))
                # Length alongside the mask, while the column still looks the way the
                # check expects. `with_columns` broadcasts the mask, losing whether it
                # answered once or once per row; this keeps the answer.
                length_alias = f"{MASK_LENGTH_PREFIX}{alias}"
                reject_alias_collision(
                    length_alias,
                    occupied_columns,
                    self.name,
                    f"the length of the mask for check '{check_spec.name}' on column '{col_name}'",
                    col_name,
                )
                mask_exprs.append(check_expr.len().alias(length_alias))
                check_masks[(col_name, check_spec.name)] = alias

        if mask_exprs:
            # The frame's own length, captured in the same pass as the mask lengths. The
            # aggregate runs after every phase, and one that drops rows would otherwise
            # make a correct mask look like it had answered once for the frame.
            reject_alias_collision(
                CHECK_TIME_LENGTH, occupied_columns, self.name, "the frame's length when the masks were built"
            )
            mask_exprs.append(pl.len().alias(CHECK_TIME_LENGTH))
            context.data = lf.with_columns(mask_exprs)
            context.internal_columns.update(e.meta.output_name() for e in mask_exprs)
            self._reject_non_boolean_masks(context, check_masks)

        context.check_masks = check_masks

        return context

    def _reject_non_boolean_masks(self, context: PipelineContext, check_masks: dict[tuple[str, str], str]) -> None:
        """Refuse a check whose expression does not answer true or false.

        Everything downstream reads these masks as booleans: enforcement inverts them,
        the report sums them, and `apply_check_null` selects on them. A check returning
        anything else reached aggregation and failed there with a Polars cast error
        naming neither the check nor the column.

        Args:
            context: Pipeline context, already carrying the mask columns.
            check_masks: Mapping of (column, check name) to mask alias.

        Raises:
            PipelineError: If any check's mask is not Boolean.
        """
        schema = context.frame_schema()
        for (col_name, check_name), alias in check_masks.items():
            dtype = schema.get(alias)
            if dtype is not None and dtype != pl.Boolean:
                raise PipelineError(
                    f"Check '{check_name}' on column '{col_name}' returned {dtype}, not a boolean. "
                    f"A check answers whether a value is valid, so its expression has to evaluate "
                    f"to true or false per row.",
                    phase=self.name,
                    column=col_name,
                )

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
                column=col_name,
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
                column=col_name,
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
                column=col_name,
            ) from e

        try:
            return check(pl.col(col_name), **(check_spec.args or {}))
        except Exception as e:
            raise PipelineError(
                f"Failed to apply check '{check_spec.name}' to column '{col_name}': {e}",
                phase=self.name,
                column=col_name,
            ) from e

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no checks are defined in schema.

        Args:
            context: Pipeline context.

        Returns:
            True if no columns have checks defined.
        """
        return not context.schema.columns_needing_check_phase
