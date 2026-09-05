"""The validation report and the error report, built from a finished run.

Both read the collected aggregates and the mask index. Neither touches the
validator, so this module sits below it.
"""

import polars as pl

from nyctea.engine.context import PipelineContext
from nyctea.engine.masks import MaskIndex
from nyctea.engine.phases import PARSING_CHECK
from nyctea.engine.results import ColumnValidationStats, ErrorReportConfig, ValidationReport
from nyctea.utils.collect import collect

__all__ = ["build_errors", "build_report"]


def build_report(context: PipelineContext, row: pl.DataFrame) -> ValidationReport:
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
    report_cols = context.report_columns()

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


def build_errors(context: PipelineContext, index: MaskIndex) -> pl.DataFrame:
    """Build error report from check masks in the requested mode.

    Uses targeted collects of only the columns needed for error reporting,
    never the full data.

    Supports three modes via ``ErrorReportConfig.mode``:

    - **summary**: ``column | check | count`` (one row per failing check)
    - **rows**: ``column | check | count | row_indices`` (adds list of failing row indices)
    - **cells**: ``column | check | row_index | value`` (one row per failing cell)

    Args:
        context: Pipeline context with error_report_config and the LazyFrame.
        index: The mask aliases, partitioned once by kind and column.

    Returns:
        DataFrame with errors in the configured format.
    """
    config = context.error_report_config or ErrorReportConfig()

    builders = {
        "summary": _build_errors_summary,
        "rows": _build_errors_rows,
        "cells": _build_errors_cells,
    }
    return builders[config.mode](context, index, config)


def _build_errors_summary(
    context: PipelineContext,
    index: MaskIndex,
    config: ErrorReportConfig,  # noqa: ARG001  # summary ignores it; the three builders share one signature
) -> pl.DataFrame:
    """Build summary error report: column | check | count.

    Single 1-row aggregation collect.
    """
    entries = index.entries
    empty_schema = {"column": pl.String, "check": pl.String, "count": pl.UInt32}
    empty = pl.DataFrame({"column": [], "check": [], "count": []}, schema=empty_schema)
    if not entries:
        return empty

    count_exprs = [(~pl.col(alias)).sum().cast(pl.UInt32).alias(alias) for _, _, alias in entries]
    counts = collect(context.data.select(count_exprs), context.aggregate_engine)

    rows: list[dict[str, str | int]] = []
    for col_name, check_name, alias in entries:
        count = int(counts[alias].item())
        if count > 0:
            rows.append({"column": col_name, "check": check_name, "count": count})

    if not rows:
        return empty
    return pl.DataFrame(rows, schema=empty_schema)


def _build_errors_rows(context: PipelineContext, index: MaskIndex, config: ErrorReportConfig) -> pl.DataFrame:
    """Build rows error report: column | check | count | row_indices.

    The failing-row count is a full aggregation, but ``row_indices`` is limited
    with ``.head(config.limit)`` inside the lazy query, before collecting, so a
    small ``limit`` also bounds how much is materialized rather than only
    truncating output. Row materialization stays on the default engine, unlike
    the summary builder's pure aggregate.
    """
    entries = index.entries
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
    if not entries:
        return empty

    exprs: list[pl.Expr] = []
    for _, _, alias in entries:
        failed = ~pl.col(alias)
        indices_expr = pl.col("__row_index__").filter(failed).cast(pl.UInt32)
        if config.limit is not None:
            indices_expr = indices_expr.head(config.limit)
        exprs.append(failed.sum().cast(pl.UInt32).alias(f"__count__{alias}"))
        exprs.append(indices_expr.implode().alias(f"__indices__{alias}"))

    row = collect(context.data.select(exprs))

    rows: list[dict[str, object]] = []
    for col_name, check_name, alias in entries:
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


def _cells_exprs(entries: tuple[tuple[str, str, str], ...], config: ErrorReportConfig) -> list[pl.Expr]:
    """Build the per-alias limited indices (and optional values) list expressions."""
    exprs: list[pl.Expr] = []
    for col_name, check_name, alias in entries:
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


def _build_errors_cells(context: PipelineContext, index: MaskIndex, config: ErrorReportConfig) -> pl.DataFrame:
    """Build cells error report: column | check | row_index (| value).

    Both ``row_index`` and ``value`` lists are limited with ``.head(config.limit)``
    inside the lazy query, before collecting, so a small ``limit`` also bounds how
    much is materialized rather than only truncating output. ``value`` is included
    only when ``config.include_values`` is set. Cell materialization stays on the
    default engine, unlike the summary builder's pure aggregate.
    """
    entries = index.entries
    empty_schema = {
        "column": pl.String,
        "check": pl.String,
        "row_index": pl.UInt32,
    }
    if config.include_values:
        empty_schema["value"] = pl.String
    empty = pl.DataFrame({name: [] for name in empty_schema}, schema=empty_schema)
    if not entries:
        return empty

    row = collect(context.data.select(_cells_exprs(entries, config)))

    parts: list[pl.DataFrame] = []
    for col_name, check_name, alias in entries:
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
