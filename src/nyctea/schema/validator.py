"""Schema validator for orchestrating validation.

This module provides the SchemaValidator class, which is the main entry point
for validation using the new validator-based pipeline architecture.
"""

from typing import Any

import polars as pl

from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.phases import COERCION_CHECK, NOT_NULL_CHECK
from nyctea.engine.pipeline import ValidationPipeline
from nyctea.engine.validate import ColumnValidationStats, ErrorReportConfig, ValidationReport, ValidationResult
from nyctea.exceptions import PipelineError
from nyctea.schema.model import AggregateEngine, SchemaModel
from nyctea.validators.registry import Registry

__all__ = ["SchemaValidator"]


def _collect(lf: pl.LazyFrame) -> pl.DataFrame:
    """Collect a LazyFrame into a DataFrame.

    Wrapper that narrows the return type for the type checker.
    Polars' collect() returns ``DataFrame | InProcessQuery`` but we never
    use ``background=True``, so the result is always a DataFrame.
    """
    result = lf.collect()
    assert isinstance(result, pl.DataFrame)
    return result


def _collect_aggregate(lf: pl.LazyFrame, engine: AggregateEngine) -> pl.DataFrame:
    """Collect a LazyFrame of pure reduction expressions (sum/len/all/any_horizontal).

    Streaming roughly halves peak memory on these (#11) with no correctness
    difference, since none of the reductions used here are approximation-based
    (unlike e.g. ``approx_n_unique``, which does disagree between engines). Not for
    row- or cell-level materialization -- those need the default engine.

    ``engine`` is decided once per ``validate()`` call (see
    ``schema.streaming_row_threshold``) and threaded in via
    ``context.aggregate_engine`` rather than hardcoded, since streaming has a fixed
    per-query setup cost that makes it slower than the default engine on small data.
    """
    result = lf.collect(engine=engine)
    assert isinstance(result, pl.DataFrame)
    return result


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

        # Create pipeline if not provided
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
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate a DataFrame against the schema.

        Failure handling is controlled by ``schema.on_failure`` (default) and
        per-column ``on_failure`` overrides. See ``SchemaModel.resolve_on_failure``.

        Args:
            df: Input DataFrame to validate.
            error_report_config: Configuration for error reporting.
            lazy: Return LazyFrame (True) or DataFrame (False). If None, uses schema.lazy.
            **kwargs: Additional validation options (reserved for future use).

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

        # Convert to LazyFrame
        lf = df.lazy() if isinstance(df, pl.DataFrame) else df

        # Add row index for error tracking
        lf = lf.with_row_index("__row_index__")

        # Create pipeline context
        context = PipelineContext(
            data=lf,
            schema=self.schema,
            registry=self.registry,
            error_report_config=error_report_config or ErrorReportConfig(),
            aggregate_engine=aggregate_engine,
        )

        # Execute pipeline (fully lazy — no collects inside phases)
        context = self.pipeline.execute(context)

        # Enforce on_failure=raise (targeted collect of counts only)
        self._enforce_coercion_raise(context)
        self._enforce_check_raise(context)

        # Build errors before nulling failures, so the report reflects the
        # original failing values (targeted collect of mask + relevant columns only)
        errors = self._build_errors(context)

        # Apply on_failure=null: null out values that failed a check
        self._apply_check_null(context)

        # Build report (targeted collect of row count only)
        report = self._build_report(context)

        # Strip only the helper columns this run generated. Prefix matching would also
        # drop a legitimate user column that happens to start with one of the prefixes.
        internal_cols = [
            c for c in context.data.collect_schema().names() if c == "__row_index__" or c in context.internal_columns
        ]
        clean = context.data.drop(internal_cols)

        # Only collect if lazy=False
        use_lazy = lazy if lazy is not None else self.schema.lazy
        final_data: pl.DataFrame | pl.LazyFrame = clean if use_lazy else _collect(clean)

        return ValidationResult(
            data=final_data,
            errors=errors,
            report=report,
        )

    def _enforce_coercion_raise(self, context: PipelineContext) -> None:
        """Raise PipelineError if on_failure=raise columns gained nulls from coercion.

        Uses a targeted collect of only the failure counts (1-row aggregation), not
        the full data.

        Args:
            context: Pipeline context with check_masks populated (CoercionPhase
                registers one coercion mask per cast column).

        Raises:
            PipelineError: If any on_failure=raise column has coercion-introduced nulls.
        """
        schema = context.schema

        raise_cols = {
            col_name: alias
            for (col_name, check_name), alias in context.check_masks.items()
            if check_name == COERCION_CHECK and schema.resolve_on_failure(col_name) == "raise"
        }
        if not raise_cols:
            return

        count_exprs = [
            (~pl.col(alias)).sum().alias(f"__new_nulls__{col_name}") for col_name, alias in raise_cols.items()
        ]
        counts = _collect_aggregate(context.data.select(count_exprs), context.aggregate_engine)
        for col_name in raise_cols:
            new_nulls = int(counts[f"__new_nulls__{col_name}"].item())
            if new_nulls > 0:
                raise PipelineError(
                    f"Coercion failed for column '{col_name}': "
                    f"{new_nulls} value(s) could not be cast to "
                    f"{schema.columns[col_name].dtype}",
                    phase="coercion",
                )

    def _check_masks_by_column(self, context: PipelineContext, on_failure: str) -> dict[str, list[str]]:
        """Group check mask aliases by column for columns resolving to the given on_failure.

        Excludes the built-in not-null check, which is already enforced directly in
        ``ColumnCheckPhase`` and can never resolve to ``'null'`` (nullable=False is
        required for that check to exist, and the guard in ``resolve_on_failure``
        rewrites ``'null'`` to ``'raise'`` for non-nullable columns; ``'ignore'`` is
        unaffected and can still apply).

        Also excludes the coercion check: it has its own raise path, and a
        coercion-failed value is already null, so nulling it again here would
        double-count it in ``nullified_counts``.

        Args:
            context: Pipeline context with populated check_masks.
            on_failure: The resolved on_failure behavior to filter columns by.

        Returns:
            Mapping of column name to the list of mask aliases for its checks.
        """
        schema = context.schema
        grouped: dict[str, list[str]] = {}
        for (col_name, check_name), alias in context.check_masks.items():
            if check_name in (NOT_NULL_CHECK, COERCION_CHECK):
                continue
            if schema.resolve_on_failure(col_name) != on_failure:
                continue
            grouped.setdefault(col_name, []).append(alias)
        return grouped

    def _enforce_check_raise(self, context: PipelineContext) -> None:
        """Raise PipelineError if any on_failure=raise column failed a check.

        Uses a targeted collect of only the per-column failure counts (1-row
        aggregation), not the full data.

        Args:
            context: Pipeline context with check_masks populated.

        Raises:
            PipelineError: If any on_failure=raise column has a failing check.
        """
        raise_cols = self._check_masks_by_column(context, "raise")
        if not raise_cols:
            return

        count_exprs = [
            pl.any_horizontal([~pl.col(alias) for alias in aliases]).sum().alias(f"__check_fail__{col_name}")
            for col_name, aliases in raise_cols.items()
        ]
        counts = _collect_aggregate(context.data.select(count_exprs), context.aggregate_engine)
        for col_name in raise_cols:
            fail_count = int(counts[f"__check_fail__{col_name}"].item())
            if fail_count > 0:
                raise PipelineError(
                    f"Check failed for column '{col_name}': {fail_count} value(s) failed "
                    f"validation and on_failure is 'raise'.",
                    phase="column_checks",
                )

    def _apply_check_null(self, context: PipelineContext) -> None:
        """Null out values that failed a check on an on_failure=null column.

        A value is nulled if any of its column's checks failed. Runs after
        ``_build_errors`` so the error report still reflects the original
        failing values.

        Args:
            context: Pipeline context with check_masks populated. Mutates
                ``context.data`` and ``context.nullified_counts`` in place.
        """
        null_cols = self._check_masks_by_column(context, "null")
        if not null_cols:
            return

        fail_exprs = {
            col_name: pl.any_horizontal([~pl.col(alias) for alias in aliases])
            for col_name, aliases in null_cols.items()
        }
        counts = _collect_aggregate(
            context.data.select(
                [expr.sum().alias(f"__check_fail__{col_name}") for col_name, expr in fail_exprs.items()]
            ),
            context.aggregate_engine,
        )
        for col_name in null_cols:
            context.nullified_counts[col_name] = context.nullified_counts.get(col_name, 0) + int(
                counts[f"__check_fail__{col_name}"].item()
            )

        null_exprs = [
            pl.when(fail_expr).then(None).otherwise(pl.col(col_name)).alias(col_name)
            for col_name, fail_expr in fail_exprs.items()
        ]
        context.data = context.data.with_columns(null_exprs)

    def _build_report(self, context: PipelineContext) -> ValidationReport:
        """Build the validation report from the same check masks used by ``_build_errors``.

        Coercion failures get their own column stat but still count toward rows_failed.

        Uses a single targeted collect of per-column/per-row aggregations, never the
        full data.

        Args:
            context: Pipeline context with check_masks and nullified_counts populated.

        Returns:
            ValidationReport with row counts and per-column statistics.
        """
        schema = context.schema
        lf = context.data
        col_names = lf.collect_schema().names()

        check_masks_by_col: dict[str, list[str]] = {}
        coercion_alias_by_col: dict[str, str] = {}
        for (col_name, check_name), alias in context.check_masks.items():
            if check_name == COERCION_CHECK:
                coercion_alias_by_col[col_name] = alias
            else:
                check_masks_by_col.setdefault(col_name, []).append(alias)

        exprs: list[pl.Expr] = [pl.len().alias("__total__")]

        for col_name, aliases in check_masks_by_col.items():
            # Sum of per-check failure counts, not distinct failing rows, so this
            # matches the totals in `errors` for the same column: a row failing two
            # checks contributes two failures here, same as two rows in `errors`.
            exprs.append(
                pl.sum_horizontal([(~pl.col(alias)).sum() for alias in aliases]).alias(f"__check_fail__{col_name}")
            )
        exprs.extend(
            (~pl.col(alias)).sum().alias(f"__coercion_fail__{col_name}")
            for col_name, alias in coercion_alias_by_col.items()
        )

        if context.check_masks:
            all_aliases = list(context.check_masks.values())
            exprs.append(pl.any_horizontal([~pl.col(alias) for alias in all_aliases]).sum().alias("__rows_failed__"))

        report_cols = [c for c in schema.columns if c in col_names]
        exprs.extend(pl.col(col_name).is_null().sum().alias(f"__final_null__{col_name}") for col_name in report_cols)

        row = _collect_aggregate(lf.select(exprs), context.aggregate_engine)

        total = int(row["__total__"].item())
        rows_failed = int(row["__rows_failed__"].item()) if "__rows_failed__" in row.columns else 0

        columns: dict[str, ColumnValidationStats] = {}
        for col_name in report_cols:
            check_fail_alias = f"__check_fail__{col_name}"
            coercion_fail_alias = f"__coercion_fail__{col_name}"
            columns[col_name] = ColumnValidationStats(
                column_name=col_name,
                coercion_failures=int(row[coercion_fail_alias].item()) if coercion_fail_alias in row.columns else 0,
                check_failures=int(row[check_fail_alias].item()) if check_fail_alias in row.columns else 0,
                nullified=context.nullified_counts.get(col_name, 0),
                final_null_count=int(row[f"__final_null__{col_name}"].item()),
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
        counts = _collect_aggregate(context.data.select(count_exprs), context.aggregate_engine)

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

        Collects only __row_index__ + mask columns. Row materialization stays on the
        default engine, unlike the summary builder's pure aggregate.
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

        mask_aliases = list(check_masks.values())
        subset = _collect(context.data.select(["__row_index__", *mask_aliases]))
        row_index = subset.get_column("__row_index__")

        rows: list[dict[str, object]] = []
        for (col_name, check_name), alias in check_masks.items():
            failed = subset.get_column(alias).not_()
            indices = row_index.filter(failed).cast(pl.UInt32).to_list()
            if not indices:
                continue
            limited = indices[: config.limit] if config.limit is not None else indices
            rows.append(
                {
                    "column": col_name,
                    "check": check_name,
                    "count": len(indices),
                    "row_indices": limited,
                }
            )

        if not rows:
            return empty
        return pl.DataFrame(rows, schema=empty_schema)

    def _build_errors_cells(self, context: PipelineContext, config: ErrorReportConfig) -> pl.DataFrame:
        """Build cells error report: column | check | row_index | value.

        Collects only __row_index__ + mask columns + data columns with failing checks.
        Cell materialization stays on the default engine, unlike the summary builder's
        pure aggregate.
        """
        check_masks = context.check_masks
        empty_schema = {
            "column": pl.String,
            "check": pl.String,
            "row_index": pl.UInt32,
            "value": pl.String,
        }
        empty = pl.DataFrame(
            {"column": [], "check": [], "row_index": [], "value": []},
            schema=empty_schema,
        )
        if not check_masks:
            return empty

        # Collect only the columns we need: row_index + masks + data columns with checks
        mask_aliases = list(check_masks.values())
        data_cols = list({col_name for (col_name, _) in check_masks})
        subset = _collect(context.data.select(["__row_index__", *mask_aliases, *data_cols]))
        row_index = subset.get_column("__row_index__")

        parts: list[pl.DataFrame] = []
        for (col_name, check_name), alias in check_masks.items():
            failed = subset.get_column(alias).not_()
            if failed.sum() == 0:
                continue

            fail_indices = row_index.filter(failed).cast(pl.UInt32)
            fail_values = subset.get_column(col_name).filter(failed).cast(pl.String)

            if config.limit is not None:
                fail_indices = fail_indices.head(config.limit)
                fail_values = fail_values.head(config.limit)

            parts.append(
                pl.DataFrame(
                    {
                        "column": [col_name] * len(fail_indices),
                        "check": [check_name] * len(fail_indices),
                        "row_index": fail_indices,
                        "value": fail_values,
                    }
                )
            )

        if not parts:
            return empty
        return pl.concat(parts)

    def customize_pipeline(self) -> ValidationPipeline:
        """Get a copy of the pipeline for customization.

        This allows users to modify the pipeline before validation.

        Returns:
            Copy of the validation pipeline.

        Example:
            >>> pipeline = validator.customize_pipeline()
            >>> pipeline.add_phase(MyCustomPhase(), after="column_parsing")
            >>> validator.pipeline = pipeline
            >>> result = validator.validate(df)
        """
        # For now, return the existing pipeline
        # In full implementation, would create a deep copy
        return self.pipeline
