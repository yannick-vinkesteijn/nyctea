"""Validation engine: applies schema steps and reports failures.

This module provides the core validation functionality for Nyctea. It orchestrates
the validation pipeline, applying parsers, type coercion, and checks to Polars
DataFrames according to schema specifications.

## Pipeline Order

The validation engine follows a fixed pipeline:

1. **Column Resolution** - Map synonym names to canonical column names
2. **Count Original Nulls** - Track null counts before any transformations
3. **Frame Parsers** - Apply DataFrame-level transformations
4. **Column Parsers** - Apply column-level string transformations
5. **Type Coercion** - Cast columns to target dtypes (happens before checks!)
6. **Frame Checks** - Apply DataFrame-level validation rules
7. **Column Checks** - Apply column-level validation rules
8. **Error Reporting** - Build error report from validation failures
9. **Nullification** - Apply lenient behavior (set failures to null where configured)
10. **Final Nullable Check** - Safety assertion for non-nullable columns
11. **Report Generation** - Build comprehensive validation statistics

## Key Classes

- `ValidationResult` - Complete validation outcome with data, errors, and report
- `ValidationReport` - Comprehensive validation statistics
- `ColumnValidationStats` - Per-column validation statistics
- `ErrorReportConfig` - Configuration for error reporting detail level
- `SchemaResolutionError` - Exception for column resolution failures

## Example

```python
from nyctea.engine import validate, ErrorReportConfig
from nyctea.schema.model import SchemaModel
from nyctea.functions import FunctionRegistry

schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": False}}})
registry = FunctionRegistry()

result = validate(df, schema, registry)
print(result.report.summary())
```
"""

from dataclasses import dataclass
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from nyctea.functions.registry import FunctionRegistry
from nyctea.schema.model import OnFailureBehavior, SchemaModel


class SchemaResolutionError(ValueError):
    """Raised when columns cannot be resolved from synonyms."""


class ErrorReportConfig(BaseModel):
    """Configuration for error reporting detail level."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["summary", "rows", "cells"] = Field(
        "summary",
        description=(
            "Error reporting mode:\n"
            "- 'summary': Column + check + count only (minimal)\n"
            "- 'rows': Add row indices where failures occurred\n"
            "- 'cells': Add row indices + actual values (maximum detail)"
        ),
    )

    limit: int | None = Field(
        None,
        description="Maximum number of error rows to return per column+check. None = unlimited.",
    )

    include_values: bool = Field(
        True,
        description="Include actual failing values in output (only applies to 'cells' mode)",
    )


class ColumnValidationStats(BaseModel):
    """Per-column validation statistics."""

    model_config = ConfigDict(extra="forbid")

    column_name: str
    parse_failures: int = 0
    coercion_failures: int = 0
    check_failures: int = 0
    nullified: int = Field(0, description="Values set to null due to failures")
    final_null_count: int = Field(0, description="Total nulls in output")
    original_null_count: int = Field(0, description="Nulls before validation")


class ValidationReport(BaseModel):
    """Comprehensive validation outcome report."""

    model_config = ConfigDict(extra="forbid")

    rows_processed: int
    rows_valid: int
    on_failure: OnFailureBehavior
    columns: dict[str, ColumnValidationStats] = Field(default_factory=dict)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Validation Report (on_failure: {self.on_failure})",
            f"Rows: {self.rows_valid}/{self.rows_processed} valid ({self.rows_valid / self.rows_processed * 100:.1f}%)",
            "",
            "Column Issues:",
        ]
        for col_name, stats in self.columns.items():
            if stats.nullified > 0 or stats.check_failures > 0:
                lines.append(f"  {col_name}:")
                if stats.coercion_failures:
                    lines.append(f"    Coercion failures: {stats.coercion_failures}")
                if stats.check_failures:
                    lines.append(f"    Check failures: {stats.check_failures}")
                if stats.nullified:
                    lines.append(f"    Nullified: {stats.nullified}")
                lines.append(f"    Final nulls: {stats.final_null_count}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation run."""

    data: pl.DataFrame | pl.LazyFrame
    errors: pl.DataFrame
    report: ValidationReport


def resolve_column_names(schema: SchemaModel, df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame | pl.LazyFrame:
    """Rename columns using canonical names and synonyms.

    Args:
        schema: SchemaModel defining columns and synonyms.
        df: Input frame.

    Returns:
        Frame with columns renamed to canonical names where possible.

    Raises:
        SchemaResolutionError: If required columns are missing or ambiguous.
    """
    columns = set(df.collect_schema().names() if isinstance(df, pl.LazyFrame) else df.columns)
    mapping: dict[str, str] = {}
    used: set[str] = set()

    for canonical, col_schema in schema.columns.items():
        candidates = {canonical} | set(col_schema.synonyms)
        found = [c for c in columns if c in candidates]
        if not found:
            if col_schema.required:
                raise SchemaResolutionError(
                    f"Required column '{canonical}' is missing (synonyms: {col_schema.synonyms})"
                )
            continue
        if len(found) > 1:
            raise SchemaResolutionError(
                f"Ambiguous columns for '{canonical}': {found}. Only one canonical/synonym is allowed."
            )
        physical = found[0]
        if physical in used:
            raise SchemaResolutionError(f"Column '{physical}' is mapped multiple times.")
        used.add(physical)
        if physical != canonical:
            mapping[physical] = canonical

    if not mapping:
        return df
    return df.rename(mapping)


def _count_original_nulls(lf: pl.LazyFrame, schema: SchemaModel) -> dict[str, int]:
    """Count nulls in original data before validation.

    Args:
        lf: Input LazyFrame (after column resolution)
        schema: Schema model

    Returns:
        Dictionary mapping column names to original null counts
    """
    count_exprs = [pl.col(col_name).is_null().sum().alias(col_name) for col_name in schema.columns.keys()]

    if not count_exprs:
        return {}

    counts_df = lf.select(count_exprs).collect()
    return {col_name: int(counts_df[col_name].item()) for col_name in schema.columns.keys()}


def _apply_frame_parsers(df: pl.LazyFrame, schema: SchemaModel, registry: FunctionRegistry) -> pl.LazyFrame:
    lf = df
    for parser in schema.frame_parsers:
        func = registry.frame_parsers.get(parser.name)
        if func is None:
            raise KeyError(f"Frame parser '{parser.name}' is not registered")
        lf = func(lf, **parser.args)
    return lf


def _apply_frame_checks(df: pl.LazyFrame, schema: SchemaModel, registry: FunctionRegistry) -> pl.LazyFrame:
    lf = df
    for check in schema.frame_checks:
        func = registry.frame_checks.get(check.name)
        if func is None:
            raise KeyError(f"Frame check '{check.name}' is not registered")
        lf = func(lf, **check.args)
    return lf


def _apply_column_parsers(df: pl.LazyFrame, schema: SchemaModel, registry: FunctionRegistry) -> pl.LazyFrame:
    lf = df
    for name, col_schema in schema.columns.items():
        if not col_schema.parsers:
            continue
        expr = pl.col(name)
        for parser in col_schema.parsers:
            func = registry.column_parsers.get(parser.name)
            if func is None:
                raise KeyError(f"Column parser '{parser.name}' is not registered")
            expr = func(expr, **parser.args)
        lf = lf.with_columns(expr.alias(name))
    return lf


def _collect_column_checks(
    df: pl.LazyFrame, schema: SchemaModel, registry: FunctionRegistry
) -> tuple[pl.LazyFrame, list[pl.Expr]]:
    """Collect all column checks, including auto-generated nullable checks.

    Args:
        df: LazyFrame to check
        schema: Schema model with check configurations
        registry: Function registry

    Returns:
        Tuple of (LazyFrame, list of failure expressions)
    """
    lf = df
    fail_exprs: list[pl.Expr] = []
    for name, col_schema in schema.columns.items():
        col_expr = pl.col(name)

        # AUTO-INJECT: non_null check if nullable=False
        if not col_schema.nullable:
            result = col_expr.is_not_null()
            fail = (~result.fill_null(False)).alias(f"{name}__non_null")
            fail_exprs.append(fail)

        # User-defined checks
        for check in col_schema.checks:
            func = registry.column_checks.get(check.name)
            if func is None:
                raise KeyError(f"Column check '{check.name}' is not registered")
            result = func(col_expr, **check.args)
            fail = (~result.fill_null(False)).alias(f"{name}__{check.name}")
            fail_exprs.append(fail)
    return lf, fail_exprs


def _resolve_dtype(dtype: object) -> pl.DataType:
    if isinstance(dtype, pl.DataType):
        return dtype
    if isinstance(dtype, str):
        candidate = getattr(pl, dtype, None)
        if candidate is None:
            raise ValueError(f"Unknown dtype string '{dtype}'")
        return candidate
    raise ValueError(f"Unsupported dtype specification: {dtype!r}")


def _apply_coercion(
    df: pl.LazyFrame,
    schema: SchemaModel,
    strategy: Literal["strict", "null_on_failure"],
) -> pl.LazyFrame:
    """Apply dtype coercion after parsing and checks.

    Args:
        df: LazyFrame to coerce.
        schema: Schema model with dtype specifications.
        strategy: How to handle coercion failures.
            - "strict": Raises on coercion failure.
            - "null_on_failure": Sets failed coercions to null (does NOT track as errors).

    Returns:
        LazyFrame with coerced columns.
    """
    if not schema.coerce:
        return df
    casts = []
    for name, col_schema in schema.columns.items():
        target = _resolve_dtype(col_schema.dtype)
        if strategy == "strict":
            casts.append(pl.col(name).cast(target).alias(name))
        elif strategy == "null_on_failure":
            casts.append(pl.col(name).cast(target, strict=False).alias(name))
        else:
            raise ValueError(f"Unsupported coerce strategy: {strategy}")
    if not casts:
        return df
    return df.with_columns(casts)


def _build_error_report(
    lf: pl.LazyFrame,
    fail_exprs: list[pl.Expr],
    config: ErrorReportConfig,
    original_df: pl.LazyFrame,
) -> pl.DataFrame:
    """Build error report based on configuration.

    Args:
        lf: LazyFrame with __row_index__ column and check expressions evaluated.
        fail_exprs: List of boolean expressions marking failures.
        config: Error reporting configuration.
        original_df: Original data (before checks) to extract values from.

    Returns:
        DataFrame with errors in the requested format.
    """
    if not fail_exprs:
        # Return empty DataFrame with appropriate schema
        if config.mode == "summary":
            return pl.DataFrame({"column": [], "check": [], "count": pl.Series([], dtype=pl.UInt32)})
        if config.mode == "rows":
            return pl.DataFrame(
                {
                    "column": [],
                    "check": [],
                    "count": pl.Series([], dtype=pl.UInt32),
                    "row_indices": pl.Series([], dtype=pl.List(pl.UInt32)),
                }
            )
        # cells
        cols = {"column": [], "check": [], "row_index": pl.Series([], dtype=pl.UInt32)}
        if config.include_values:
            cols["value"] = []
        return pl.DataFrame(cols)

    # Collect check results
    error_table = lf.select([pl.col("__row_index__").alias("row_index"), *fail_exprs]).collect()

    # Melt to long format
    melted = error_table.melt(id_vars="row_index", variable_name="check_col", value_name="failed")

    # Filter to only failures and split column__check format
    failures = (
        melted.filter(pl.col("failed"))
        .with_columns(pl.col("check_col").str.split_exact("__", 1).alias("parts"))
        .with_columns(
            pl.col("parts").struct.field("field_0").alias("column"),
            pl.col("parts").struct.field("field_1").alias("check"),
        )
        .drop("parts", "check_col", "failed")
    )

    if failures.is_empty():
        # Return empty with proper schema
        if config.mode == "summary":
            return pl.DataFrame({"column": [], "check": [], "count": pl.Series([], dtype=pl.UInt32)})
        if config.mode == "rows":
            return pl.DataFrame(
                {
                    "column": [],
                    "check": [],
                    "count": pl.Series([], dtype=pl.UInt32),
                    "row_indices": pl.Series([], dtype=pl.List(pl.UInt32)),
                }
            )
        cols = {"column": [], "check": [], "row_index": pl.Series([], dtype=pl.UInt32)}
        if config.include_values:
            cols["value"] = []
        return pl.DataFrame(cols)

    # Mode: summary - just counts
    if config.mode == "summary":
        return failures.group_by("column", "check").agg(pl.len().alias("count")).sort(["column", "check"])

    # Mode: rows - counts + list of row indices
    if config.mode == "rows":
        grouped = (
            failures.group_by("column", "check")
            .agg([pl.len().alias("count"), pl.col("row_index").sort().alias("row_indices")])
            .sort(["column", "check"])
        )

        # Apply limit if specified
        if config.limit is not None:
            grouped = grouped.with_columns(
                pl.col("row_indices").list.head(config.limit),
                pl.when(pl.col("count") > config.limit)
                .then(pl.lit(config.limit))
                .otherwise(pl.col("count"))
                .alias("count"),
            )

        return grouped

    # Mode: cells - individual rows with optional values
    # cells
    # Apply limit per column+check if specified
    if config.limit is not None:
        failures = (
            failures.with_columns(pl.col("row_index").rank("dense").over(["column", "check"]).alias("_rank"))
            .filter(pl.col("_rank") <= config.limit)
            .drop("_rank")
        )

    # Add actual values if requested
    if config.include_values:
        # Collect original data with row indices
        original_with_idx = original_df.select(
            [pl.col("__row_index__").alias("row_index"), pl.all().exclude("__row_index__")]
        ).collect()

        # For each unique column, join to get values
        result_parts = []
        for col_name in failures["column"].unique().to_list():
            col_failures = failures.filter(pl.col("column") == col_name)

            # Join with original data to get values
            with_values = col_failures.join(
                original_with_idx.select(["row_index", col_name]), on="row_index", how="left"
            ).rename({col_name: "value"})

            result_parts.append(with_values)

        failures = pl.concat(result_parts).sort(["column", "check", "row_index"])

    return failures.sort(["column", "check", "row_index"])


def _apply_lenient_checks(
    lf: pl.LazyFrame,
    fail_exprs: list[pl.Expr],
    schema: SchemaModel,
) -> tuple[pl.LazyFrame, dict[str, int]]:
    """Apply lenient check behavior: nullify failing values when on_failure='null'.

    Args:
        lf: LazyFrame with data
        fail_exprs: List of boolean failure expressions (from _collect_column_checks)
        schema: Schema model

    Returns:
        Tuple of (modified LazyFrame, dict of nullified counts per column)
    """
    if not fail_exprs:
        return lf, {}

    # Collect check results
    check_results = lf.select([pl.col("__row_index__"), *fail_exprs]).collect()

    # Build nullification plan
    nullifications: dict[str, pl.Expr] = {}
    nullified_counts: dict[str, int] = {}

    for fail_expr in fail_exprs:
        check_col_name = fail_expr.meta.output_name()
        parts = check_col_name.split("__", 1)
        if len(parts) != 2:
            continue
        col_name, check_name = parts

        # Check if this column uses lenient mode
        on_failure = schema.resolve_on_failure(col_name)
        if on_failure != "null":
            continue

        # Accumulate failure masks (OR multiple checks)
        fail_mask = pl.col(check_col_name)
        if col_name in nullifications:
            nullifications[col_name] = nullifications[col_name] | fail_mask
        else:
            nullifications[col_name] = fail_mask

    # Apply nullifications
    if nullifications:
        # Build list of failure mask column names to join
        fail_mask_cols = list(nullifications.values())
        fail_mask_names = [expr.meta.output_name() for expr in fail_mask_cols]

        # Join check results back to data (convert DataFrame to LazyFrame)
        lf = lf.join(check_results.select(["__row_index__"] + fail_mask_names).lazy(), on="__row_index__", how="left")

        # Build nullification expressions
        null_exprs = []
        for col_name, fail_mask_expr in nullifications.items():
            fail_mask_name = fail_mask_expr.meta.output_name()

            # Count nullifications (check_results is already a DataFrame)
            count_val = check_results.select(pl.col(fail_mask_name).sum().alias("count"))["count"].item()
            nullified_counts[col_name] = int(count_val)

            # Nullify expression using the joined mask column
            null_expr = pl.when(pl.col(fail_mask_name)).then(None).otherwise(pl.col(col_name)).alias(col_name)
            null_exprs.append(null_expr)

        lf = lf.with_columns(null_exprs)
        # Drop the temporary failure mask columns
        lf = lf.drop(*fail_mask_names)

    return lf, nullified_counts


def _check_final_nullable(
    lf: pl.LazyFrame,
    schema: SchemaModel,
) -> None:
    """Final assertion: ensure no nulls in nullable=False columns.

    This is a safety check after nullification to catch any logic errors.
    Should never fail if on_failure validation worked correctly.

    Args:
        lf: LazyFrame after nullification
        schema: Schema model

    Raises:
        ValueError: If any nullable=False column contains nulls
    """
    for col_name, col_schema in schema.columns.items():
        if not col_schema.nullable:
            null_count = lf.select(pl.col(col_name).is_null().sum()).collect().item()
            if null_count > 0:
                raise ValueError(
                    f"Column '{col_name}' has nullable=False but contains {null_count} null values. "
                    f"This should not happen - check on_failure configuration."
                )


def validate(
    df: pl.DataFrame | pl.LazyFrame,
    schema: SchemaModel,
    registry: FunctionRegistry,
    *,
    lazy: bool | None = None,
    coerce_strategy: Literal["strict", "null_on_failure"] = "strict",
    error_report: ErrorReportConfig | None = None,
) -> ValidationResult:
    """Validate a frame according to the schema and registry.

    Pipeline order (NEW):
    1. Column resolution (synonyms)
    2. Count original nulls
    3. Frame parsers
    4. Column parsers
    5. COERCE (moved before checks)
    6. Frame checks
    7. Column checks (with auto-injected non_null)
    8. Build error report (before nullification)
    9. Apply lenient behavior (nullify failures)
    10. Final nullable check (safety)
    11. Build validation report
    12. Return

    Args:
        df: Input DataFrame or LazyFrame.
        schema: Schema model.
        registry: Function registry holding parsers/checks.
        lazy: Optional override for lazy execution. Defaults to schema.lazy.
        coerce_strategy: How to handle coercion failures.
            - "strict": Raises on coercion failure.
            - "null_on_failure": Casts with strict=False (nulls on failure).
        error_report: Error reporting configuration. Defaults to summary mode.

    Returns:
        ValidationResult with validated data, errors DataFrame, and validation report.

    Examples:
        >>> # Summary mode (default) - just counts
        >>> result = validate(df, schema, registry)
        >>> result.errors
        shape: (2, 3)
        ┌──────────┬───────────┬───────┐
        │ column   │ check     │ count │
        │ ---      │ ---       │ ---   │
        │ str      │ str       │ u32   │
        ╞══════════╪═══════════╪═══════╡
        │ age      │ positive  │ 5     │
        │ name     │ non_null  │ 12    │
        └──────────┴───────────┴───────┘

        >>> # Rows mode - counts + indices
        >>> config = ErrorReportConfig(mode="rows", limit=100)
        >>> result = validate(df, schema, registry, error_report=config)
        >>> result.errors
        shape: (2, 3)
        ┌──────────┬───────────┬───────┬──────────────┐
        │ column   │ check     │ count │ row_indices  │
        │ ---      │ ---       │ ---   │ ---          │
        │ str      │ str       │ u32   │ list[u32]    │
        ╞══════════╪═══════════╪═══════╪══════════════╡
        │ age      │ positive  │ 5     │ [0, 3, 5,…]  │
        │ name     │ non_null  │ 12    │ [1, 2, 7,…]  │
        └──────────┴───────────┴───────┴──────────────┘

        >>> # Cells mode - individual rows with values
        >>> config = ErrorReportConfig(mode="cells", include_values=True, limit=10)
        >>> result = validate(df, schema, registry, error_report=config)
        >>> result.errors
        shape: (17, 4)
        ┌──────────┬───────────┬───────────┬────────┐
        │ column   │ check     │ row_index │ value  │
        │ ---      │ ---       │ ---       │ ---    │
        │ str      │ str       │ u32       │ i64    │
        ╞══════════╪═══════════╪═══════════╪════════╡
        │ age      │ positive  │ 0         │ -5     │
        │ age      │ positive  │ 3         │ 0      │
        │ name     │ non_null  │ 1         │ null   │
        │ …        │ …         │ …         │ …      │
        └──────────┴───────────┴───────────┴────────┘
    """
    if error_report is None:
        error_report = ErrorReportConfig(mode="summary")

    use_lazy = schema.lazy if lazy is None else lazy
    lf: pl.LazyFrame = df.lazy() if isinstance(df, pl.DataFrame) else df
    lf = lf.with_row_index("__row_index__")

    total_rows = int(lf.select(pl.len()).collect().item())

    # Phase 1: Column resolution
    lf = resolve_column_names(schema, lf)

    # Phase 2: Count original nulls (BEFORE any transformations)
    original_nulls = _count_original_nulls(lf, schema)

    # Phase 3: Frame parsers
    lf = _apply_frame_parsers(lf, schema, registry)

    # Phase 4: Column parsers (string transformations)
    lf = _apply_column_parsers(lf, schema, registry)

    # Phase 5: COERCE (MOVED BEFORE CHECKS)
    # Track coercion failures when using lenient strategy
    coercion_failures = {}
    if schema.coerce:
        if coerce_strategy == "null_on_failure":
            # Count nulls before coercion
            try:
                before_nulls = {
                    col: int(lf.select(pl.col(col).is_null().sum()).collect().item()) for col in schema.columns.keys()
                }
            except pl.exceptions.SchemaError as e:
                # Provide helpful error message for dtype mismatches
                current_dtypes = lf.collect_schema()
                schema_dtypes = {name: _resolve_dtype(col.dtype) for name, col in schema.columns.items()}

                error_details = []
                for col_name in schema.columns.keys():
                    current = current_dtypes.get(col_name)
                    expected = schema_dtypes.get(col_name)
                    if current and expected and current != expected:
                        error_details.append(f"  - {col_name}: current type is {current}, schema expects {expected}")

                raise ValueError(
                    "Schema dtype mismatch after parsers. This often happens when:\n"
                    "1. Column parsers (e.g., to_int, to_float) already convert the dtype\n"
                    "2. The schema's dtype doesn't match what the parsers produce\n\n"
                    "Mismatched columns:\n" + "\n".join(error_details) + "\n\n"
                    f"Solutions:\n"
                    f"  - Remove parsers and rely on coercion alone, OR\n"
                    f"  - Update schema dtypes to match parser outputs (Int64 -> i64, Float64 -> f64), OR\n"
                    f"  - Set coerce: false if parsers handle all type conversions\n\n"
                    f"Original error: {e}"
                ) from e

            lf = _apply_coercion(lf, schema, coerce_strategy)
            for col in schema.columns.keys():
                after = int(lf.select(pl.col(col).is_null().sum()).collect().item())
                coercion_failures[col] = after - before_nulls[col]
        else:
            try:
                lf = _apply_coercion(lf, schema, coerce_strategy)
            except pl.exceptions.SchemaError as e:
                # Provide helpful error message for dtype mismatches
                current_dtypes = lf.collect_schema()
                schema_dtypes = {name: _resolve_dtype(col.dtype) for name, col in schema.columns.items()}

                error_details = []
                for col_name in schema.columns.keys():
                    current = current_dtypes.get(col_name)
                    expected = schema_dtypes.get(col_name)
                    if current and expected and current != expected:
                        error_details.append(f"  - {col_name}: current type is {current}, schema expects {expected}")

                raise ValueError(
                    "Schema dtype mismatch after parsers. This often happens when:\n"
                    "1. Column parsers (e.g., to_int, to_float) already convert the dtype\n"
                    "2. The schema's dtype doesn't match what the parsers produce\n\n"
                    "Mismatched columns:\n" + "\n".join(error_details) + "\n\n"
                    f"Solutions:\n"
                    f"  - Remove parsers and rely on coercion alone, OR\n"
                    f"  - Update schema dtypes to match parser outputs (Int64 -> i64, Float64 -> f64), OR\n"
                    f"  - Set coerce: false if parsers handle all type conversions\n\n"
                    f"Original error: {e}"
                ) from e

    # Phase 6: Frame checks
    lf = _apply_frame_checks(lf, schema, registry)

    # Keep copy before checks for error value extraction
    lf_before_checks = lf

    # Phase 7: Column checks (with auto-injected non_null for nullable=False)
    lf, check_exprs = _collect_column_checks(lf, schema, registry)

    # Phase 8: Build error report BEFORE nullification (captures ALL failures)
    errors_df = _build_error_report(lf, check_exprs, error_report, lf_before_checks)

    # Phase 9: Apply lenient behavior (nullify where on_failure='null')
    lf, nullified_counts = _apply_lenient_checks(lf, check_exprs, schema)

    # Phase 10: Final nullable check (safety assertion)
    _check_final_nullable(lf, schema)

    # Phase 11: Count final nulls
    final_nulls = {col: int(lf.select(pl.col(col).is_null().sum()).collect().item()) for col in schema.columns.keys()}

    # Phase 12: Build validation report
    column_stats = {}
    for col_name in schema.columns.keys():
        # Count check failures from error report
        if not errors_df.is_empty():
            col_check_fails = errors_df.filter(pl.col("column") == col_name)
            check_fail_count = int(col_check_fails.select(pl.col("count").sum()).item() or 0)
        else:
            check_fail_count = 0

        column_stats[col_name] = ColumnValidationStats(
            column_name=col_name,
            parse_failures=0,  # Not tracked yet
            coercion_failures=coercion_failures.get(col_name, 0),
            check_failures=check_fail_count,
            nullified=nullified_counts.get(col_name, 0),
            final_null_count=final_nulls.get(col_name, 0),
            original_null_count=original_nulls.get(col_name, 0),
        )

    # Calculate valid rows
    if errors_df.is_empty():
        valid_rows = total_rows
    # Conservative: total - unique failing rows
    elif error_report.mode == "cells":
        failed_row_count = len(errors_df.select(pl.col("row_index").unique()).collect())
        valid_rows = total_rows - failed_row_count
    else:
        valid_rows = max(0, total_rows - int(errors_df.select(pl.col("count").sum()).item() or 0))

    validation_report = ValidationReport(
        rows_processed=total_rows,
        rows_valid=valid_rows,
        on_failure=schema.on_failure,
        columns=column_stats,
    )

    # Phase 13: Clean up and return
    lf = lf.drop("__row_index__")
    data_out: pl.DataFrame | pl.LazyFrame = lf if use_lazy else lf.collect()

    return ValidationResult(
        data=data_out,
        errors=errors_df,
        report=validation_report,
    )


__all__ = [
    "ColumnValidationStats",
    "ErrorReportConfig",
    "SchemaResolutionError",
    "ValidationReport",
    "ValidationResult",
    "resolve_column_names",
    "validate",
]
