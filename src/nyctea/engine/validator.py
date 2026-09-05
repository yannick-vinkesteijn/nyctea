"""Validation run orchestration.

This module provides the DataValidator class, which drives one validation run:
it builds the pipeline for a schema, executes it against the data, and assembles
the report. It reads the schema and never modifies it.
"""

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.masks import MaskIndex, index_masks, resolving_to
from nyctea.engine.pipeline import ValidationPipeline
from nyctea.engine.reporting import build_errors, build_report
from nyctea.engine.results import ErrorReportConfig, ValidationResult
from nyctea.exceptions import PipelineError
from nyctea.schema.model import SchemaModel
from nyctea.utils import occupied_columns
from nyctea.utils.collect import collect, pick_aggregate_engine
from nyctea.validators.registry import Registry

__all__ = ["DataValidator"]


@dataclass(frozen=True)
class _RaiseRule:
    """One on_failure=raise aggregate, paired with what to raise when it is non-zero.

    ``message`` takes the collected count because three of the four kinds interpolate
    it and the not-null one deliberately does not. The kind and column it was built
    from are already baked into ``alias`` and into the closure.
    """

    alias: str
    phase: str
    message: Callable[[int], str]


def build_aggregate_exprs(
    context: PipelineContext,
    index: MaskIndex,
    null_fail_exprs: dict[str, pl.Expr],
) -> tuple[list[pl.Expr], list[_RaiseRule]]:
    """Build every aggregate expression for the single collect, and the raise plan.

    The plan pairs each on_failure=raise aggregate with the message and phase to
    raise when it comes back non-zero, so the caller reads the collected row once
    in pipeline order instead of re-deriving four sets of aliases with f-strings.

    Args:
        context: Pipeline context with check_masks populated.
        index: The mask aliases, partitioned once by kind and column.
        null_fail_exprs: Column name to combined-failure expression, for on_failure=null columns.

    Returns:
        The aliased aggregate expressions to select in one pass, and the raise
        rules to apply to the collected row, in pipeline order.
    """
    schema = context.schema

    exprs: list[pl.Expr] = [pl.len().alias("__total__")]
    exprs.extend((~pl.col(alias)).sum().alias(f"__parsing_fail__{col}") for col, alias in index.parsing.items())
    exprs.extend((~pl.col(alias)).sum().alias(f"__coercion_fail__{col}") for col, alias in index.coercion.items())
    for col, aliases in index.reported.items():
        # Sum of per-check failure counts, not distinct failing rows, so this
        # matches the totals in `errors` for the same column: a row failing two
        # checks contributes two failures here, same as two rows in `errors`.
        exprs.append(pl.sum_horizontal([(~pl.col(a)).sum() for a in aliases]).alias(f"__check_fail__{col}"))
    exprs.extend(fail_expr.sum().alias(f"__nullify__{col}") for col, fail_expr in null_fail_exprs.items())
    if index.all_aliases:
        exprs.append(pl.any_horizontal([~pl.col(alias) for alias in index.all_aliases]).sum().alias("__rows_failed__"))

    for col_name in context.report_columns():
        # Reflects the null count *after* nullification, without needing the
        # mutation to have happened yet: replicate the same when/then the
        # mutation will apply, rather than adding pre-null and nullified counts
        # (which would double-count a value that was already null and also
        # mask-failed).
        null_expr = pl.col(col_name)
        if col_name in null_fail_exprs:
            null_expr = pl.when(null_fail_exprs[col_name]).then(None).otherwise(null_expr)
        exprs.append(null_expr.is_null().sum().alias(f"__final_null__{col_name}"))

    # Parsing and coercion raises read the per-column failure counts already
    # selected above, so a raise column does not pay for the same sum twice.
    # Not-null and check raises need their own aggregate.
    notnull_raise = resolving_to(index.notnull, schema, "raise")
    check_raise = resolving_to(index.declared, schema, "raise")
    exprs.extend((~pl.col(alias)).sum().alias(f"__notnull_raise__{col}") for col, alias in notnull_raise.items())
    exprs.extend(
        pl.any_horizontal([~pl.col(alias) for alias in aliases]).sum().alias(f"__raise_fail__{col}")
        for col, aliases in check_raise.items()
    )

    # Pipeline order. Which message a caller sees when a column fails two kinds
    # at once is decided here and nowhere else.
    raise_plan: list[_RaiseRule] = [
        _RaiseRule(
            f"__parsing_fail__{col}",
            "column_parsing",
            lambda n, c=col: f"Parsing failed for column '{c}': {n} non-null value(s) became null.",
        )
        for col in resolving_to(index.parsing, schema, "raise")
    ]
    raise_plan += [
        _RaiseRule(
            f"__coercion_fail__{col}",
            "coercion",
            lambda n, c=col, d=schema.columns[col].dtype: (
                f"Coercion failed for column '{c}': {n} value(s) could not be cast to {d}"
            ),
        )
        for col in resolving_to(index.coercion, schema, "raise")
    ]
    raise_plan += [
        _RaiseRule(
            f"__notnull_raise__{col}",
            "column_checks",
            lambda _n, c=col: f"Column '{c}' has nullable=False but contains null values.",
        )
        for col in notnull_raise
    ]
    raise_plan += [
        _RaiseRule(
            f"__raise_fail__{col}",
            "column_checks",
            lambda n, c=col: (
                f"Check failed for column '{c}': {n} value(s) failed validation and on_failure is 'raise'."
            ),
        )
        for col in check_raise
    ]

    return exprs, raise_plan


def run_aggregates_and_raise(context: PipelineContext, index: MaskIndex) -> tuple[pl.DataFrame, dict[str, pl.Expr]]:
    """Collect every non-row-level aggregate this validate() call needs in one pass.

    Combines what were previously four separate collects -- coercion-raise counts,
    check-raise counts, on_failure=null fail counts, and the report's own
    aggregates -- into a single ``select()`` on the aggregate engine, since none of
    them need row-level data and all run against the same lazy graph. ``_build_errors``
    stays a separate collect: its row/cell modes need the default engine, not the
    aggregate engine (see ``_collect``'s docstring).

    Args:
        context: Pipeline context with check_masks populated.
        index: The mask aliases, partitioned once by kind and column.

    Returns:
        Tuple of the collected aggregate row and the on_failure=null fail
        expressions, needed by the caller to apply nullification afterward
        without a second collect.

    Raises:
        PipelineError: If any on_failure=raise column has parser- or
            coercion-introduced nulls, or a failing check.
    """
    schema = context.schema
    null_fail_exprs = {
        col: pl.any_horizontal([~pl.col(alias) for alias in aliases])
        for col, aliases in resolving_to(index.declared, schema, "null").items()
    }

    exprs, raise_plan = build_aggregate_exprs(context, index, null_fail_exprs)
    aggregates = context.data.select(exprs)
    original_data = context.original_data if context.original_data is not None else context.data
    original_columns = set(original_data.collect_schema().names())
    original_null_exprs = [
        pl.col(col_name).is_null().sum().alias(f"__original_null__{col_name}")
        for col_name in schema.columns
        if col_name in original_columns
    ]
    if original_null_exprs:
        aggregates = aggregates.join(original_data.select(original_null_exprs), how="cross")
    row = collect(aggregates, context.aggregate_engine)

    for rule in raise_plan:
        count = int(row[rule.alias].item())
        if count > 0:
            raise PipelineError(rule.message(count), phase=rule.phase)

    return row, null_fail_exprs


def apply_check_null(context: PipelineContext, row: pl.DataFrame, null_fail_exprs: dict[str, pl.Expr]) -> None:
    """Null out values that failed a check on an on_failure=null column.

    Uses the nullify counts already collected by ``_run_aggregates_and_raise``;
    applying the ``.with_columns()`` mutation itself stays fully lazy, no collect.
    Runs after ``_build_errors`` so the error report still reflects the original
    failing values.

    Args:
        context: Pipeline context. Mutates ``context.data`` and
            ``context.nullified_counts`` in place.
        row: The aggregate row from ``_run_aggregates_and_raise``.
        null_fail_exprs: Per-column on_failure=null fail expressions, from
            ``_run_aggregates_and_raise``.
    """
    if not null_fail_exprs:
        return

    for col_name in null_fail_exprs:
        context.nullified_counts[col_name] = context.nullified_counts.get(col_name, 0) + int(
            row[f"__nullify__{col_name}"].item()
        )

    null_exprs = [
        pl.when(fail_expr).then(None).otherwise(pl.col(col_name)).alias(col_name)
        for col_name, fail_expr in null_fail_exprs.items()
    ]
    context.data = context.data.with_columns(null_exprs)


class DataValidator:
    """Validates data against a schema using the validator pipeline.

    This class orchestrates the validation process, managing the pipeline
    and providing a clean API for validation.

    Attributes:
        schema: Schema definition.
        registry: Validator registry.
        pipeline: Validation pipeline.

    Example:
        >>> from nyctea.schema.model import SchemaModel
        >>> from nyctea.validators.registry import Registry
        >>>
        >>> schema = SchemaModel.from_yaml("schema.yaml")
        >>> registry = Registry()
        >>> # ... register validators ...
        >>>
        >>> validator = DataValidator(schema, registry)
        >>> result = validator.validate(df)
    """

    def __init__(
        self,
        schema: SchemaModel,
        registry: Registry,
        pipeline: ValidationPipeline | None = None,
    ) -> None:
        """Initialize schema validator.

        Args:
            schema: Schema definition.
            registry: Validator registry with parsers and checks.
            pipeline: Custom pipeline (if None, creates from schema).
        """
        self.schema = schema
        self.registry = registry

        if pipeline is None:
            self.pipeline = create_pipeline_from_schema(schema)
        else:
            self.pipeline = pipeline

    def validate(
        self,
        df: pl.DataFrame | pl.LazyFrame,
        *,
        error_report_config: ErrorReportConfig | None = None,
        lazy: bool | None = None,
    ) -> ValidationResult:
        """Validate a DataFrame against the schema.

        Failure handling is controlled by ``schema.on_failure`` (default) and
        per-column ``on_failure`` overrides. See ``SchemaModel.resolve_on_failure``.

        Args:
            df: Input DataFrame to validate.
            error_report_config: Configuration for error reporting.
            lazy: Return LazyFrame (True) or DataFrame (False). If None, uses schema.lazy.

        Returns:
            ValidationResult with validated data, errors, and report.

        Raises:
            ValidationError: If validation fails for on_failure=raise columns.
            PipelineError: If pipeline execution fails.

        Example:
            >>> result = validator.validate(df)
            >>> if result.errors is not None:
            ...     print(f"Found {len(result.errors)} errors")
            >>> print(result.report.summary())
        """
        # Decided from the original df (before the LazyFrame conversion below), since
        # only the eager form has a free row count to threshold on.
        aggregate_engine = pick_aggregate_engine(df, self.schema.streaming_row_threshold)

        lf = df.lazy() if isinstance(df, pl.DataFrame) else df

        if "__row_index__" in occupied_columns(lf.collect_schema().names(), self.schema.accepted_names):
            raise PipelineError(
                "Cannot build row tracking: the data or schema already contains "
                "a column named '__row_index__'. Rename it before validating.",
                phase="row_tracking",
            )
        lf = lf.with_row_index("__row_index__")

        context = PipelineContext(
            data=lf,
            schema=self.schema,
            registry=self.registry,
            error_report_config=error_report_config or ErrorReportConfig(),
            aggregate_engine=aggregate_engine,
            original_data=lf,
        )
        # Row tracking is a generated helper like any other, so it is recorded in
        # one place rather than special-cased at strip time.
        context.internal_columns.add("__row_index__")

        # Execute pipeline. Phases build the lazy graph without collecting.
        context = self.pipeline.execute(context)

        # Single collect for every aggregate this call needs: on_failure=raise counts
        # (coercion and check), on_failure=null fail counts, and the report's own
        # aggregates. Raises PipelineError here if any on_failure=raise column failed.
        index = index_masks(context.check_masks)
        row, null_fail_exprs = run_aggregates_and_raise(context, index)

        # Build errors before nulling failures, so the report reflects the
        # original failing values (targeted collect of mask + relevant columns only)
        errors = build_errors(context, index)

        # Apply on_failure=null: null out values that failed a check (no collect,
        # reuses the counts already collected above)
        apply_check_null(context, row, null_fail_exprs)

        # Build report from the row already collected above
        report = build_report(context, row)

        # Strip only the helper columns this run generated. Prefix matching would also
        # drop a legitimate user column that happens to start with one of the prefixes.
        # strict=False because a custom pipeline may drop a helper before this point.
        clean = context.data.drop(sorted(context.internal_columns), strict=False)

        # Only collect if lazy=False
        use_lazy = lazy if lazy is not None else self.schema.lazy
        final_data: pl.DataFrame | pl.LazyFrame = clean if use_lazy else collect(clean)

        return ValidationResult(
            data=final_data,
            errors=errors,
            report=report,
        )
