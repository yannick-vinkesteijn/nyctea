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

if TYPE_CHECKING:
    from nyctea.engine.pipeline import ValidationPipeline
    from nyctea.plugins.registry import MasterRegistry
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
        >>> from nyctea.plugins.registry import MasterRegistry
        >>>
        >>> schema = SchemaModel.from_yaml("schema.yaml")
        >>> registry = MasterRegistry()
        >>> # ... register plugins ...
        >>>
        >>> validator = SchemaValidator(schema, registry)
        >>> result = validator.validate(df)
    """

    def __init__(
        self,
        schema: SchemaModel,
        registry: MasterRegistry,
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
        coerce_strategy: str = "strict",
        error_report_config: ErrorReportConfig | None = None,
        lazy: bool | None = None,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate a DataFrame against the schema.

        Args:
            df: Input DataFrame to validate.
            coerce_strategy: How to handle coercion failures ("strict" or "null_on_failure").
            error_report_config: Configuration for error reporting.
            lazy: Return LazyFrame (True) or DataFrame (False). If None, uses schema.lazy.
            **kwargs: Additional validation options (reserved for future use).

        Returns:
            ValidationResult with validated data, errors, and report.

        Raises:
            ValidationError: If validation fails in strict mode.
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
            coerce_strategy=coerce_strategy,
            error_report_config=error_report_config or ErrorReportConfig(),
        )

        # Execute pipeline
        context = self.pipeline.execute(context)

        # Remove row index
        context.data = context.data.drop("__row_index__")

        # Build minimal report (in full implementation, this would be done by ReportGenerationPhase)
        report = self._build_report(context)

        # Collect if needed
        use_lazy = lazy if lazy is not None else self.schema.lazy
        final_data = context.data if use_lazy else context.data.collect()

        # Build minimal errors DataFrame (in full implementation, this would be done by ErrorReportingPhase)
        errors = self._build_errors(context)

        return ValidationResult(
            data=final_data,
            errors=errors,
            report=report,
        )

    def _build_report(self, context: PipelineContext) -> ValidationReport:
        """Build validation report from context.

        This is a minimal implementation. In the full version, this would be
        done by ReportGenerationPhase.

        Args:
            context: Pipeline context.

        Returns:
            Validation report.
        """
        # Count total rows
        total_rows = context.data.select(pl.len()).collect().item()

        # Count rows with check failures
        failed_rows = 0
        if context.check_failures:
            # In full implementation, would track which rows failed
            failed_rows = sum(context.check_failures.values())

        valid_rows = max(0, total_rows - failed_rows)

        return ValidationReport(
            rows_processed=total_rows,
            rows_valid=valid_rows,
            profile_used=context.schema.profile,
            columns={},  # In full implementation, would populate column stats
        )

    def _build_errors(self, context: PipelineContext) -> pl.DataFrame:
        """Build errors DataFrame from context.

        This is a minimal implementation. In the full version, this would be
        done by ErrorReportingPhase.

        Args:
            context: Pipeline context.

        Returns:
            Errors DataFrame or empty DataFrame if no errors.
        """
        if not context.check_failures:
            # No errors - return empty DataFrame with expected schema
            return pl.DataFrame({
                "column": [],
                "check": [],
                "failures": [],
            })

        # Build simple error summary
        errors_data = {
            "column": [],
            "check": [],
            "failures": [],
        }

        for (col_name, check_name), count in context.check_failures.items():
            errors_data["column"].append(col_name)
            errors_data["check"].append(check_name)
            errors_data["failures"].append(count)

        return pl.DataFrame(errors_data)

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
