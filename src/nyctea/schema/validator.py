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

        # Single collect at API boundary
        collected: pl.DataFrame = context.data.collect()  # type: ignore[assignment]

        # Enforce on_failure=raise for coercion failures
        self._enforce_coercion_raise(context, collected)

        # Build report and errors from collected data
        report = self._build_report(context, collected)
        errors = self._build_errors(context, collected)

        # Strip internal columns (__row_index__, __check__*, __pre_null__*)
        internal_cols = [c for c in collected.columns if c.startswith(("__check__", "__pre_null__", "__row_index__"))]
        clean = collected.drop(internal_cols)

        # Return lazy or eager based on preference
        use_lazy = lazy if lazy is not None else self.schema.lazy
        final_data: pl.DataFrame | pl.LazyFrame = clean.lazy() if use_lazy else clean

        return ValidationResult(
            data=final_data,
            errors=errors,
            report=report,
        )

    def _enforce_coercion_raise(self, context: PipelineContext, collected: pl.DataFrame) -> None:
        """Raise PipelineError if on_failure=raise columns gained nulls from coercion.

        Args:
            context: Pipeline context.
            collected: Collected DataFrame with __pre_null__ mask columns.

        Raises:
            PipelineError: If any on_failure=raise column has coercion-introduced nulls.
        """
        schema = context.schema
        for col_name in schema.columns:
            pre_null_col = f"__pre_null__{col_name}"
            if pre_null_col not in collected.columns:
                continue

            behavior = schema.resolve_on_failure(col_name)
            if behavior != "raise":
                continue

            # New nulls = currently null AND was not null before cast
            pre_null = collected.get_column(pre_null_col)
            post_null = collected.get_column(col_name).is_null()
            new_nulls = (post_null & ~pre_null).sum()

            if new_nulls > 0:
                raise PipelineError(
                    f"Coercion failed for column '{col_name}': "
                    f"{new_nulls} value(s) could not be cast to "
                    f"{schema.columns[col_name].dtype}",
                    phase="coercion",
                )

    def _build_report(self, context: PipelineContext, collected: pl.DataFrame) -> ValidationReport:
        """Stub — row counts only. Replaced by ReportGenerationPhase (Step 4)."""
        total = len(collected)
        return ValidationReport(
            rows_processed=total,
            rows_valid=total,
            on_failure=context.schema.on_failure,
            columns={},
        )

    def _build_errors(self, context: PipelineContext, collected: pl.DataFrame) -> pl.DataFrame:
        """Stub — summary from masks. Replaced by ErrorReportingPhase (Step 3)."""
        empty = pl.DataFrame(
            {"column": [], "check": [], "failures": []},
            schema={"column": pl.String, "check": pl.String, "failures": pl.UInt32},
        )
        if not context.check_masks:
            return empty

        rows: list[dict[str, str | int]] = []
        for (col_name, check_name), alias in context.check_masks.items():
            count = int(collected.get_column(alias).not_().sum())
            if count > 0:
                rows.append({"column": col_name, "check": check_name, "failures": count})

        if not rows:
            return empty

        return pl.DataFrame(
            rows,
            schema={"column": pl.String, "check": pl.String, "failures": pl.UInt32},
        )

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
