"""Schema validator for orchestrating validation.

This module provides the SchemaValidator class, which is the main entry point
for validation using the new plugin-based pipeline architecture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.validate import ErrorReportConfig, ValidationReport, ValidationResult
from nyctea.exceptions import PipelineError

if TYPE_CHECKING:
    from nyctea.engine.pipeline import ValidationPipeline
    from nyctea.plugins.registry import Registry
    from nyctea.schema.model import SchemaModel

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


class SchemaValidator:
    """Validates data against a schema using the plugin pipeline.

    This class orchestrates the validation process, managing the pipeline
    and providing a clean API for validation.

    Attributes:
        schema: Schema definition.
        registry: Plugin registry.
        pipeline: Validation pipeline.

    Example:
        >>> from nyctea.schema.model import SchemaModel
        >>> from nyctea.plugins.registry import Registry
        >>>
        >>> schema = SchemaModel.from_yaml("schema.yaml")
        >>> registry = Registry()
        >>> # ... register plugins ...
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
            registry: Plugin registry with parsers and checks.
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
        )

        # Execute pipeline (fully lazy — no collects inside phases)
        context = self.pipeline.execute(context)

        # Enforce on_failure=raise (targeted collect of counts only)
        self._enforce_coercion_raise(context)

        # Build errors (targeted collect of mask + relevant columns only)
        errors = self._build_errors(context)

        # Build report (targeted collect of row count only)
        report = self._build_report(context)

        # Strip internal columns (lazy)
        internal_cols = [
            c
            for c in context.data.collect_schema().names()
            if c.startswith(("__check__", "__pre_null__", "__row_index__"))
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

        Uses a targeted collect of only the new-null counts (1-row aggregation),
        not the full data.

        Args:
            context: Pipeline context with LazyFrame containing __pre_null__ masks.

        Raises:
            PipelineError: If any on_failure=raise column has coercion-introduced nulls.
        """
        schema = context.schema
        lf = context.data
        col_names = lf.collect_schema().names()

        count_exprs: list[pl.Expr] = []
        raise_cols: list[str] = []

        for col_name in schema.columns:
            pre_null_col = f"__pre_null__{col_name}"
            if pre_null_col not in col_names:
                continue
            if schema.resolve_on_failure(col_name) != "raise":
                continue

            expr = (pl.col(col_name).is_null() & ~pl.col(pre_null_col)).sum().alias(f"__new_nulls__{col_name}")
            count_exprs.append(expr)
            raise_cols.append(col_name)

        if not count_exprs:
            return

        counts = _collect(lf.select(count_exprs))
        for col_name in raise_cols:
            new_nulls = int(counts[f"__new_nulls__{col_name}"].item())
            if new_nulls > 0:
                raise PipelineError(
                    f"Coercion failed for column '{col_name}': "
                    f"{new_nulls} value(s) could not be cast to "
                    f"{schema.columns[col_name].dtype}",
                    phase="coercion",
                )

    def _build_report(self, context: PipelineContext) -> ValidationReport:
        """Stub — row counts only. Replaced by ReportGenerationPhase (Step 4)."""
        total = int(_collect(context.data.select(pl.len())).item())
        return ValidationReport(
            rows_processed=total,
            rows_valid=total,
            on_failure=context.schema.on_failure,
            columns={},
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
        return builders[config.mode](context.check_masks, context.data, config)

    def _build_errors_summary(
        self,
        check_masks: dict[tuple[str, str], str],
        lf: pl.LazyFrame,
        config: ErrorReportConfig,
    ) -> pl.DataFrame:
        """Build summary error report: column | check | count.

        Single 1-row aggregation collect.
        """
        empty_schema = {"column": pl.String, "check": pl.String, "count": pl.UInt32}
        empty = pl.DataFrame({"column": [], "check": [], "count": []}, schema=empty_schema)
        if not check_masks:
            return empty

        count_exprs = [(~pl.col(alias)).sum().cast(pl.UInt32).alias(alias) for alias in check_masks.values()]
        counts = _collect(lf.select(count_exprs))

        rows: list[dict[str, str | int]] = []
        for (col_name, check_name), alias in check_masks.items():
            count = int(counts[alias].item())
            if count > 0:
                rows.append({"column": col_name, "check": check_name, "count": count})

        if not rows:
            return empty
        return pl.DataFrame(rows, schema=empty_schema)

    def _build_errors_rows(
        self,
        check_masks: dict[tuple[str, str], str],
        lf: pl.LazyFrame,
        config: ErrorReportConfig,
    ) -> pl.DataFrame:
        """Build rows error report: column | check | count | row_indices.

        Collects only __row_index__ + mask columns.
        """
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
        subset = _collect(lf.select(["__row_index__", *mask_aliases]))
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

    def _build_errors_cells(
        self,
        check_masks: dict[tuple[str, str], str],
        lf: pl.LazyFrame,
        config: ErrorReportConfig,
    ) -> pl.DataFrame:
        """Build cells error report: column | check | row_index | value.

        Collects only __row_index__ + mask columns + data columns with failing checks.
        """
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
        subset = _collect(lf.select(["__row_index__", *mask_aliases, *data_cols]))
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
