"""Validation run orchestration.

This module provides the SchemaValidator class, which drives one validation run:
it builds the pipeline for a schema, executes it against the data, and assembles
the report. It reads the schema and never modifies it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import polars as pl

from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.phases import COERCION_CHECK, NOT_NULL_CHECK, PARSING_CHECK
from nyctea.engine.pipeline import ValidationPipeline
from nyctea.engine.results import ColumnValidationStats, ErrorReportConfig, ValidationReport, ValidationResult
from nyctea.exceptions import PipelineError
from nyctea.schema.model import SchemaModel
from nyctea.types import AggregateEngine
from nyctea.utils import occupied_columns
from nyctea.validators.registry import Registry

__all__ = ["SchemaValidator"]


def _collect(lf: pl.LazyFrame, engine: AggregateEngine | None = None) -> pl.DataFrame:
    """Collect a LazyFrame, on a specific engine when one is given.

    The engine cannot simply be passed through. Polars' own default is
    ``engine='auto'``, and ``engine=None`` is a ValueError rather than a request for
    that default, so the unset case has to call ``collect()`` with no argument.

    ``engine`` is for pure reductions (sum/len/all/any_horizontal) only. Streaming
    roughly halves peak memory on those (#11) with no correctness difference, since
    none of the reductions used here are approximation-based (unlike e.g.
    ``approx_n_unique``, which does disagree between engines). Row- and cell-level
    materialization needs the default engine, so it leaves ``engine`` unset. The
    value is decided once per ``validate()`` call (see ``schema.streaming_row_threshold``)
    and threaded in via ``context.aggregate_engine`` rather than hardcoded, since
    streaming has a fixed per-query setup cost that makes it slower than the default
    engine on small data.
    """
    return lf.collect() if engine is None else lf.collect(engine=engine)


def _pick_aggregate_engine(df: pl.DataFrame | pl.LazyFrame, threshold: int) -> AggregateEngine:
    """Decide the engine for this validate() call's internal aggregate collects.

    A LazyFrame input's size is unknown without collecting, and choosing lazy is
    itself a signal of larger/out-of-core intent, so it always gets streaming. An
    eager DataFrame's row count is free (``.height``), so it only pays streaming's
    setup cost once the data is actually large enough to benefit.
    """
    if isinstance(df, pl.DataFrame) and df.height < threshold:
        return "in-memory"
    return "streaming"


_Aliases = TypeVar("_Aliases", str, list[str])


def _resolving_to(columns: dict[str, _Aliases], schema: SchemaModel, on_failure: str) -> dict[str, _Aliases]:
    """The subset of ``columns`` whose resolved on_failure behaviour is ``on_failure``."""
    return {col: value for col, value in columns.items() if schema.resolve_on_failure(col) == on_failure}


@dataclass(frozen=True)
class _MaskIndex:
    """``context.check_masks`` partitioned once, by kind and by column.

    ``declared`` holds user-declared checks only. Parser, coercion and built-in
    not-null failures are excluded because each has its own enforcement and report
    accounting. Their failed values are already null, so nulling them again through
    an ``on_failure='null'`` column would double-count them in ``nullified_counts``.
    The not-null check can never resolve to ``'null'`` in any case: it exists only
    for non-nullable columns, whose ``'null'`` behaviour resolves to ``'raise'``.

    ``reported`` is the wider grouping behind the per-column ``check_failures`` stat,
    which does count a not-null failure as a check failure.
    """

    parsing: dict[str, str]
    coercion: dict[str, str]
    notnull: dict[str, str]
    declared: dict[str, list[str]]
    reported: dict[str, list[str]]
    all_aliases: list[str]


def _index_masks(check_masks: dict[tuple[str, str], str]) -> _MaskIndex:
    """Partition the mask aliases in one pass over ``check_masks``."""
    parsing: dict[str, str] = {}
    coercion: dict[str, str] = {}
    notnull: dict[str, str] = {}
    declared: dict[str, list[str]] = {}
    reported: dict[str, list[str]] = {}
    for (col_name, check_name), alias in check_masks.items():
        if check_name == PARSING_CHECK:
            parsing[col_name] = alias
        elif check_name == COERCION_CHECK:
            coercion[col_name] = alias
        else:
            reported.setdefault(col_name, []).append(alias)
            if check_name == NOT_NULL_CHECK:
                notnull[col_name] = alias
            else:
                declared.setdefault(col_name, []).append(alias)
    return _MaskIndex(parsing, coercion, notnull, declared, reported, list(check_masks.values()))


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


class SchemaValidator:
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
        >>> validator = SchemaValidator(schema, registry)
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
        aggregate_engine = _pick_aggregate_engine(df, self.schema.streaming_row_threshold)

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
        row, null_fail_exprs = self._run_aggregates_and_raise(context)

        # Build errors before nulling failures, so the report reflects the
        # original failing values (targeted collect of mask + relevant columns only)
        errors = self._build_errors(context)

        # Apply on_failure=null: null out values that failed a check (no collect,
        # reuses the counts already collected above)
        self._apply_check_null(context, row, null_fail_exprs)

        # Build report from the row already collected above
        report = self._build_report(context, row)

        # Strip only the helper columns this run generated. Prefix matching would also
        # drop a legitimate user column that happens to start with one of the prefixes.
        # strict=False because a custom pipeline may drop a helper before this point.
        clean = context.data.drop(sorted(context.internal_columns), strict=False)

        # Only collect if lazy=False
        use_lazy = lazy if lazy is not None else self.schema.lazy
        final_data: pl.DataFrame | pl.LazyFrame = clean if use_lazy else _collect(clean)

        return ValidationResult(
            data=final_data,
            errors=errors,
            report=report,
        )

    def _build_aggregate_exprs(
        self,
        context: PipelineContext,
        index: _MaskIndex,
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
        col_names = context.get_column_names()

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
            exprs.append(
                pl.any_horizontal([~pl.col(alias) for alias in index.all_aliases]).sum().alias("__rows_failed__")
            )

        for col_name in (c for c in schema.columns if c in col_names):
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
        notnull_raise = _resolving_to(index.notnull, schema, "raise")
        check_raise = _resolving_to(index.declared, schema, "raise")
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
            for col in _resolving_to(index.parsing, schema, "raise")
        ]
        raise_plan += [
            _RaiseRule(
                f"__coercion_fail__{col}",
                "coercion",
                lambda n, c=col, d=schema.columns[col].dtype: (
                    f"Coercion failed for column '{c}': {n} value(s) could not be cast to {d}"
                ),
            )
            for col in _resolving_to(index.coercion, schema, "raise")
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

    def _run_aggregates_and_raise(self, context: PipelineContext) -> tuple[pl.DataFrame, dict[str, pl.Expr]]:
        """Collect every non-row-level aggregate this validate() call needs in one pass.

        Combines what were previously four separate collects -- coercion-raise counts,
        check-raise counts, on_failure=null fail counts, and the report's own
        aggregates -- into a single ``select()`` on the aggregate engine, since none of
        them need row-level data and all run against the same lazy graph. ``_build_errors``
        stays a separate collect: its row/cell modes need the default engine, not the
        aggregate engine (see ``_collect``'s docstring).

        Args:
            context: Pipeline context with check_masks populated.

        Returns:
            Tuple of the collected aggregate row and the on_failure=null fail
            expressions, needed by the caller to apply nullification afterward
            without a second collect.

        Raises:
            PipelineError: If any on_failure=raise column has parser- or
                coercion-introduced nulls, or a failing check.
        """
        schema = context.schema
        index = _index_masks(context.check_masks)
        null_fail_exprs = {
            col: pl.any_horizontal([~pl.col(alias) for alias in aliases])
            for col, aliases in _resolving_to(index.declared, schema, "null").items()
        }

        exprs, raise_plan = self._build_aggregate_exprs(context, index, null_fail_exprs)
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
        row = _collect(aggregates, context.aggregate_engine)

        for rule in raise_plan:
            count = int(row[rule.alias].item())
            if count > 0:
                raise PipelineError(rule.message(count), phase=rule.phase)

        return row, null_fail_exprs

    def _apply_check_null(
        self, context: PipelineContext, row: pl.DataFrame, null_fail_exprs: dict[str, pl.Expr]
    ) -> None:
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

    def _build_report(self, context: PipelineContext, row: pl.DataFrame) -> ValidationReport:
        """Build the validation report from the aggregate row already collected.

        Parser and coercion failures get their own column stats but still count
        toward rows_failed.

        Args:
            context: Pipeline context with check_masks and nullified_counts populated.
            row: The aggregate row from ``_run_aggregates_and_raise``.

        Returns:
            ValidationReport with row counts and per-column statistics.
        """
        schema = context.schema
        col_names = context.get_column_names()
        report_cols = [c for c in schema.columns if c in col_names]

        total = int(row["__total__"].item())
        rows_failed = int(row["__rows_failed__"].item()) if "__rows_failed__" in row.columns else 0

        columns: dict[str, ColumnValidationStats] = {}
        for col_name in report_cols:
            check_fail_alias = f"__check_fail__{col_name}"
            parsing_fail_alias = f"__parsing_fail__{col_name}"
            coercion_fail_alias = f"__coercion_fail__{col_name}"
            original_null_alias = f"__original_null__{col_name}"
            columns[col_name] = ColumnValidationStats(
                column_name=col_name,
                parse_failures=int(row[parsing_fail_alias].item()) if parsing_fail_alias in row.columns else 0,
                coercion_failures=int(row[coercion_fail_alias].item()) if coercion_fail_alias in row.columns else 0,
                check_failures=int(row[check_fail_alias].item()) if check_fail_alias in row.columns else 0,
                nullified=context.nullified_counts.get(col_name, 0),
                final_null_count=int(row[f"__final_null__{col_name}"].item()),
                original_null_count=int(row[original_null_alias].item()) if original_null_alias in row.columns else 0,
            )

        return ValidationReport(
            rows_processed=total,
            rows_valid=total - rows_failed,
            on_failure=schema.on_failure,
            columns=columns,
        )

    def _build_errors(self, context: PipelineContext) -> pl.DataFrame:
        """Build error report from check masks in the requested mode.

        Uses targeted collects of only the columns needed for error reporting,
        never the full data.

        Supports three modes via ``ErrorReportConfig.mode``:

        - **summary**: ``column | check | count`` (one row per failing check)
        - **rows**: ``column | check | count | row_indices`` (adds list of failing row indices)
        - **cells**: ``column | check | row_index | value`` (one row per failing cell)

        Args:
            context: Pipeline context with check_masks, error_report_config, and LazyFrame.

        Returns:
            DataFrame with errors in the configured format.
        """
        config = context.error_report_config or ErrorReportConfig()

        builders = {
            "summary": self._build_errors_summary,
            "rows": self._build_errors_rows,
            "cells": self._build_errors_cells,
        }
        return builders[config.mode](context, config)

    def _build_errors_summary(self, context: PipelineContext, config: ErrorReportConfig) -> pl.DataFrame:
        """Build summary error report: column | check | count.

        Single 1-row aggregation collect.
        """
        check_masks = context.check_masks
        empty_schema = {"column": pl.String, "check": pl.String, "count": pl.UInt32}
        empty = pl.DataFrame({"column": [], "check": [], "count": []}, schema=empty_schema)
        if not check_masks:
            return empty

        count_exprs = [(~pl.col(alias)).sum().cast(pl.UInt32).alias(alias) for alias in check_masks.values()]
        counts = _collect(context.data.select(count_exprs), context.aggregate_engine)

        rows: list[dict[str, str | int]] = []
        for (col_name, check_name), alias in check_masks.items():
            count = int(counts[alias].item())
            if count > 0:
                rows.append({"column": col_name, "check": check_name, "count": count})

        if not rows:
            return empty
        return pl.DataFrame(rows, schema=empty_schema)

    def _build_errors_rows(self, context: PipelineContext, config: ErrorReportConfig) -> pl.DataFrame:
        """Build rows error report: column | check | count | row_indices.

        The failing-row count is a full aggregation, but ``row_indices`` is limited
        with ``.head(config.limit)`` inside the lazy query, before collecting, so a
        small ``limit`` also bounds how much is materialized rather than only
        truncating output. Row materialization stays on the default engine, unlike
        the summary builder's pure aggregate.
        """
        check_masks = context.check_masks
        empty_schema = {
            "column": pl.String,
            "check": pl.String,
            "count": pl.UInt32,
            "row_indices": pl.List(pl.UInt32),
        }
        empty = pl.DataFrame(
            {"column": [], "check": [], "count": [], "row_indices": []},
            schema=empty_schema,
        )
        if not check_masks:
            return empty

        exprs: list[pl.Expr] = []
        for alias in check_masks.values():
            failed = ~pl.col(alias)
            indices_expr = pl.col("__row_index__").filter(failed).cast(pl.UInt32)
            if config.limit is not None:
                indices_expr = indices_expr.head(config.limit)
            exprs.append(failed.sum().cast(pl.UInt32).alias(f"__count__{alias}"))
            exprs.append(indices_expr.implode().alias(f"__indices__{alias}"))

        row = _collect(context.data.select(exprs))

        rows: list[dict[str, object]] = []
        for (col_name, check_name), alias in check_masks.items():
            count = int(row[f"__count__{alias}"].item())
            if count == 0:
                continue
            rows.append(
                {
                    "column": col_name,
                    "check": check_name,
                    "count": count,
                    "row_indices": row[f"__indices__{alias}"].item().to_list(),
                }
            )

        if not rows:
            return empty
        return pl.DataFrame(rows, schema=empty_schema)

    @staticmethod
    def _cells_exprs(check_masks: dict[tuple[str, str], str], config: ErrorReportConfig) -> list[pl.Expr]:
        """Build the per-alias limited indices (and optional values) list expressions."""
        exprs: list[pl.Expr] = []
        for (col_name, check_name), alias in check_masks.items():
            failed = ~pl.col(alias)
            indices_expr = pl.col("__row_index__").filter(failed).cast(pl.UInt32)
            if config.limit is not None:
                indices_expr = indices_expr.head(config.limit)
            exprs.append(indices_expr.implode().alias(f"__indices__{alias}"))
            if config.include_values:
                value_column = f"__pre_parse_value__{col_name}" if check_name == PARSING_CHECK else col_name
                values_expr = pl.col(value_column).filter(failed).cast(pl.String)
                if config.limit is not None:
                    values_expr = values_expr.head(config.limit)
                exprs.append(values_expr.implode().alias(f"__values__{alias}"))
        return exprs

    def _build_errors_cells(self, context: PipelineContext, config: ErrorReportConfig) -> pl.DataFrame:
        """Build cells error report: column | check | row_index (| value).

        Both ``row_index`` and ``value`` lists are limited with ``.head(config.limit)``
        inside the lazy query, before collecting, so a small ``limit`` also bounds how
        much is materialized rather than only truncating output. ``value`` is included
        only when ``config.include_values`` is set. Cell materialization stays on the
        default engine, unlike the summary builder's pure aggregate.
        """
        check_masks = context.check_masks
        empty_schema = {
            "column": pl.String,
            "check": pl.String,
            "row_index": pl.UInt32,
        }
        if config.include_values:
            empty_schema["value"] = pl.String
        empty = pl.DataFrame({name: [] for name in empty_schema}, schema=empty_schema)
        if not check_masks:
            return empty

        row = _collect(context.data.select(self._cells_exprs(check_masks, config)))

        parts: list[pl.DataFrame] = []
        for (col_name, check_name), alias in check_masks.items():
            indices = row[f"__indices__{alias}"].item().to_list()
            if not indices:
                continue

            part: dict[str, object] = {
                "column": [col_name] * len(indices),
                "check": [check_name] * len(indices),
                "row_index": indices,
            }
            if config.include_values:
                part["value"] = row[f"__values__{alias}"].item().to_list()

            parts.append(pl.DataFrame(part, schema=empty_schema))

        if not parts:
            return empty
        return pl.concat(parts)
