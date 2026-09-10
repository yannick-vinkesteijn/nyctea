"""Per-column parsers, and the masks that record their failures."""

import polars as pl

from nyctea.engine.checks import PARSING_CHECK
from nyctea.engine.context import PipelineContext
from nyctea.engine.phases.common import reject_alias_collision, reserved_columns
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError

__all__ = ["ColumnParsingPhase"]


class ColumnParsingPhase(PipelinePhase):
    """Apply column parsers (transformations).

    This phase applies all column-level parsers defined in the schema,
    using the validator registry to look up parser implementations.

    Dependencies: column_resolution (needs resolved names)
    """

    def __init__(self) -> None:
        """Initialize column parsing phase."""
        super().__init__(
            name="column_parsing",
            phase_type=PhaseType.PARSING,
            dependencies=["column_resolution"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply column parsers.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with parsed columns.

        Raises:
            PipelineError: If parser execution fails.
        """
        schema = context.schema
        registry = context.registry
        lf = context.data
        current_columns = set(context.get_column_names())

        # Build the parser expressions before adding snapshots and failure masks.
        transformations: list[pl.Expr] = []
        parsed_columns: list[str] = []
        reserved = reserved_columns(context)
        capture_error_values = (
            context.error_report_config is not None
            and context.error_report_config.mode == "cells"
            and context.error_report_config.include_values
        )

        for col_name in schema.columns_with_parsers:
            if col_name not in current_columns:
                continue

            pre_null_alias = f"__pre_parse_null__{col_name}"
            parse_ok_alias = f"__parse_ok__{col_name}"
            reject_alias_collision(
                pre_null_alias,
                reserved,
                self.name,
                f"the pre-parser null snapshot for column '{col_name}'",
            )
            reject_alias_collision(
                parse_ok_alias,
                reserved,
                self.name,
                f"the parser failure mask for column '{col_name}'",
            )
            if capture_error_values:
                reject_alias_collision(
                    f"__pre_parse_value__{col_name}",
                    reserved,
                    self.name,
                    f"the pre-parser error value for column '{col_name}'",
                )

            # Start with the column
            expr = pl.col(col_name)

            # Chain parsers
            for parser_spec in schema.column(col_name).parsers:
                # Look up parser validator
                try:
                    parser = registry.column_parsers.get(parser_spec.name)
                except KeyError as e:
                    raise PipelineError(
                        f"Parser '{parser_spec.name}' not found in registry. "
                        f"Available: {registry.column_parsers.list_names()}",
                        phase=self.name,
                    ) from e

                # Apply parser with arguments
                args = parser_spec.args or {}
                try:
                    expr = parser(expr, **args)
                except Exception as e:
                    raise PipelineError(
                        f"Failed to apply parser '{parser_spec.name}' to column '{col_name}': {e}",
                        phase=self.name,
                    ) from e

            # Add transformed column to batch
            transformations.append(expr.alias(col_name))
            parsed_columns.append(col_name)

        # Apply snapshots, transformations, and failure masks in dependency order
        # because each expression group depends on the columns created before it.
        if transformations:
            pre_null_exprs = [
                pl.col(col_name).is_null().alias(f"__pre_parse_null__{col_name}") for col_name in parsed_columns
            ]
            if capture_error_values:
                pre_null_exprs.extend(
                    pl.col(col_name).alias(f"__pre_parse_value__{col_name}") for col_name in parsed_columns
                )
            context.data = lf.with_columns(pre_null_exprs).with_columns(transformations)

            parse_ok_exprs = [
                (pl.col(f"__pre_parse_null__{col_name}") | pl.col(col_name).is_not_null()).alias(
                    f"__parse_ok__{col_name}"
                )
                for col_name in parsed_columns
            ]
            context.data = context.data.with_columns(parse_ok_exprs)
            context.internal_columns.update(
                alias
                for col_name in parsed_columns
                for alias in (f"__pre_parse_null__{col_name}", f"__parse_ok__{col_name}")
            )
            if capture_error_values:
                context.internal_columns.update(f"__pre_parse_value__{col_name}" for col_name in parsed_columns)
            context.check_masks.update(
                {(col_name, PARSING_CHECK): f"__parse_ok__{col_name}" for col_name in parsed_columns}
            )

        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no parsers are defined in schema.

        Args:
            context: Pipeline context.

        Returns:
            True if no columns have parsers defined.
        """
        return not context.schema.columns_with_parsers
