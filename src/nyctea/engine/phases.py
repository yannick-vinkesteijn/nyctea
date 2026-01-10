"""Concrete pipeline phase implementations.

This module contains the actual phase implementations that make up the
validation pipeline. Each phase is responsible for a specific step in
the validation process.

This is a minimal implementation with core phases. Additional phases
will be added in future iterations.
"""


from typing import TYPE_CHECKING

import polars as pl

from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.exceptions import PipelineError, ValidationError

if TYPE_CHECKING:
    from nyctea.engine.context import PipelineContext

__all__ = [
    "ColumnCheckPhase",
    "ColumnParsingPhase",
    "ColumnResolutionPhase",
]


class ColumnResolutionPhase(PipelinePhase):
    """Resolve column names using synonyms.

    This phase maps physical column names to canonical schema names using
    the synonym definitions in the schema.

    Dependencies: None (always runs first)
    """

    def __init__(self) -> None:
        """Initialize column resolution phase."""
        super().__init__(
            name="column_resolution",
            phase_type=PhaseType.RESOLUTION,
            dependencies=[],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Resolve column names using schema synonyms.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with resolved column names.

        Raises:
            ValidationError: If required columns are missing or ambiguous.
        """
        schema = context.schema
        lf = context.data

        # Get current columns
        current_columns = set(lf.collect_schema().names())

        # Build mapping from physical to canonical names
        mapping: dict[str, str] = {}
        used: set[str] = set()

        for canonical, col_schema in schema.columns.items():
            # Candidates include canonical name and all synonyms
            candidates = {canonical} | set(col_schema.synonyms)

            # Find which candidates exist in the data
            found = [c for c in current_columns if c in candidates]

            if not found:
                if col_schema.required:
                    raise ValidationError(
                        f"Required column '{canonical}' is missing. "
                        f"Looked for: {sorted(candidates)}",
                        column=canonical,
                        phase=self.name,
                    )
                continue

            if len(found) > 1:
                raise ValidationError(
                    f"Ambiguous columns for '{canonical}': {found}. "
                    "Only one canonical/synonym is allowed.",
                    column=canonical,
                    phase=self.name,
                )

            physical = found[0]

            # Check for duplicate mappings
            if physical in used:
                raise ValidationError(
                    f"Column '{physical}' is mapped multiple times.",
                    phase=self.name,
                )

            used.add(physical)

            # Only add to mapping if renaming is needed
            if physical != canonical:
                mapping[physical] = canonical

        # Apply renaming if needed
        if mapping:
            context.data = lf.rename(mapping)

        return context


class ColumnParsingPhase(PipelinePhase):
    """Apply column parsers (transformations).

    This phase applies all column-level parsers defined in the schema,
    using the plugin registry to look up parser implementations.

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

        # Collect all transformations to apply in batch
        transformations: list[pl.Expr] = []

        for col_name, col_schema in schema.columns.items():
            if not col_schema.parsers:
                continue

            # Start with the column
            expr = pl.col(col_name)

            # Chain parsers
            for parser_spec in col_schema.parsers:
                # Look up parser plugin
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
                        f"Failed to apply parser '{parser_spec.name}' "
                        f"to column '{col_name}': {e}",
                        phase=self.name,
                    ) from e

            # Add transformed column to batch
            transformations.append(expr.alias(col_name))

        # Apply all transformations in a single with_columns call
        if transformations:
            context.data = lf.with_columns(transformations)

        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no parsers are defined in schema.

        Args:
            context: Pipeline context.

        Returns:
            True if no columns have parsers defined.
        """
        return not any(
            col_schema.parsers
            for col_schema in context.schema.columns.values()
        )


class ColumnCheckPhase(PipelinePhase):
    """Apply column checks (validations).

    This phase applies all column-level checks defined in the schema,
    collecting validation errors for the error report.

    Dependencies: column_parsing (checks run after transformations)
    """

    def __init__(self) -> None:
        """Initialize column check phase."""
        super().__init__(
            name="column_checks",
            phase_type=PhaseType.CHECKING,
            dependencies=["column_parsing"],
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

        # Track check failures
        check_failures: dict[tuple[str, str], int] = {}

        for col_name, col_schema in schema.columns.items():
            # Auto-inject non_null check if nullable=False
            checks_to_run = list(col_schema.checks) if col_schema.checks else []

            if not col_schema.nullable:
                # Add implicit non_null check if not already present
                has_non_null = any(c.name == "non_null" for c in checks_to_run)
                if not has_non_null:
                    # We'll handle nullable checking in a simple way for now
                    # In the full implementation, this would use a proper Check object
                    pass

            if not checks_to_run:
                continue

            # Apply each check
            for check_spec in checks_to_run:
                # Look up check plugin
                try:
                    check = registry.column_checks.get(check_spec.name)
                except KeyError as e:
                    raise PipelineError(
                        f"Check '{check_spec.name}' not found in registry. "
                        f"Available: {registry.column_checks.list_names()}",
                        phase=self.name,
                    ) from e

                # Apply check with arguments
                args = check_spec.args or {}
                try:
                    check_expr = check(pl.col(col_name), **args)
                except Exception as e:
                    raise PipelineError(
                        f"Failed to apply check '{check_spec.name}' "
                        f"to column '{col_name}': {e}",
                        phase=self.name,
                    ) from e

                # Count failures (values where check returned False)
                # For now, we'll track this in context but not fail
                # In full implementation, this would build error DataFrame
                failure_count_expr = lf.select(
                    (~check_expr).sum().alias("failures"),
                )
                failure_count = failure_count_expr.collect().item()

                if failure_count > 0:
                    check_failures[(col_name, check_spec.name)] = failure_count

        # Store check failures in context
        context.check_failures = check_failures

        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no checks are defined in schema.

        Args:
            context: Pipeline context.

        Returns:
            True if no columns have checks defined.
        """
        return not any(
            col_schema.checks or not col_schema.nullable
            for col_schema in context.schema.columns.values()
        )
