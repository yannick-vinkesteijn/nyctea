"""Concrete pipeline phase implementations.

This module contains the actual phase implementations that make up the
validation pipeline. Each phase is responsible for a specific step in
the validation process.

This is a minimal implementation with core phases. Additional phases
will be added in future iterations.
"""

import polars as pl

from nyctea.engine.context import PipelineContext
from nyctea.engine.pipeline import PhaseType, PipelinePhase
from nyctea.engine.utils import _resolve_dtype
from nyctea.exceptions import PipelineError, ValidationError
from nyctea.schema.model import SchemaModel

NOT_NULL_CHECK = "not_null"
"""Check name reported for a nullable=False column that contains nulls. Frozen, see test_phases.py."""

COERCION_CHECK = "coerce"
"""Check name reported for a failed dtype cast. Frozen, see test_phases.py."""


def _reject_alias_collision(alias: str, current_columns: list[str], phase: str, what: str) -> None:
    """Raise if a generated internal column would overwrite a real input column.

    Args:
        alias: Generated internal column name.
        current_columns: Column names currently present in the data.
        phase: Phase name, for the error.
        what: Human description of what the alias is for.

    Raises:
        PipelineError: If the alias collides with an existing column.
    """
    if alias in current_columns:
        raise PipelineError(
            f"Cannot build {what}: the input data already contains a column named "
            f"'{alias}'. Rename it before validating.",
            phase=phase,
        )


__all__ = [
    "CoercionPhase",
    "ColumnCheckPhase",
    "ColumnParsingPhase",
    "ColumnResolutionPhase",
    "FrameCheckPhase",
    "FrameParsingPhase",
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
                        f"Required column '{canonical}' is missing. Looked for: {sorted(candidates)}",
                        column=canonical,
                        phase=self.name,
                    )
                continue

            if len(found) > 1:
                raise ValidationError(
                    f"Ambiguous columns for '{canonical}': {found}. Only one canonical/synonym is allowed.",
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


class FrameParsingPhase(PipelinePhase):
    """Apply frame-level parsers (whole-DataFrame transformations).

    Runs before column parsing, so frame parsers see the data first (they may
    add/drop rows or columns other parsers then operate on).

    Dependencies: column_resolution
    """

    def __init__(self) -> None:
        """Initialize frame parsing phase."""
        super().__init__(
            name="frame_parsing",
            phase_type=PhaseType.PARSING,
            dependencies=["column_resolution"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply frame parsers in schema-declared order.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with the frame parsers applied.

        Raises:
            PipelineError: If a frame parser is unregistered or fails.
        """
        registry = context.registry
        lf = context.data

        for parser_spec in context.schema.frame_parsers:
            try:
                parser = registry.frame_parsers.get(parser_spec.name)
            except KeyError as e:
                raise PipelineError(
                    f"Frame parser '{parser_spec.name}' not found in registry. "
                    f"Available: {registry.frame_parsers.list_names()}",
                    phase=self.name,
                ) from e

            try:
                lf = parser(lf, **parser_spec.args)
            except Exception as e:
                raise PipelineError(
                    f"Frame parser '{parser_spec.name}' failed: {e}",
                    phase=self.name,
                ) from e

        context.data = lf
        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if the schema defines no frame parsers.

        Args:
            context: Pipeline context.

        Returns:
            True if no frame parsers are defined.
        """
        return not context.schema.frame_parsers


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

        # Collect all transformations to apply in batch
        transformations: list[pl.Expr] = []

        for col_name, col_schema in schema.columns.items():
            if not col_schema.parsers:
                continue

            # Start with the column
            expr = pl.col(col_name)

            # Chain parsers
            for parser_spec in col_schema.parsers:
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
        return not any(col_schema.parsers for col_schema in context.schema.columns.values())


class CoercionPhase(PipelinePhase):
    """Cast columns to their declared dtypes.

    Runs after parsing so parsers operate on raw strings, and before checks
    so checks operate on typed data. Skipped when ``schema.coerce`` is False.

    Always casts with ``strict=False``. Pre-coercion null masks
    (``__pre_null__{col}``) are added for every cast column so the validator
    can detect coercion-introduced nulls at collect time and enforce
    per-column ``on_failure`` behavior.

    Dependencies: column_resolution
    """

    def __init__(self) -> None:
        """Initialize coercion phase."""
        super().__init__(
            name="coercion",
            phase_type=PhaseType.COERCION,
            dependencies=["column_resolution"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Cast columns to their schema-declared dtypes.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with coerced columns.

        Raises:
            PipelineError: If dtype is invalid.
        """
        schema = context.schema
        lf = context.data

        current_dtypes = lf.collect_schema()
        cast_exprs: list[pl.Expr] = []

        for col_name, col_schema in schema.columns.items():
            if col_name not in current_dtypes:
                continue

            if not schema.resolve_coerce(col_name):
                continue

            try:
                target = _resolve_dtype(col_schema.dtype)
            except ValueError as e:
                raise PipelineError(
                    f"Invalid dtype '{col_schema.dtype}' for column '{col_name}': {e}",
                    phase=self.name,
                ) from e

            if current_dtypes[col_name] == target:
                continue

            cast_exprs.append(pl.col(col_name).cast(target, strict=False).alias(col_name))

        if not cast_exprs:
            return context

        # Snapshot null state before casting so coercion-introduced nulls
        # can be detected at collect time.
        cols_to_cast = [expr.meta.output_name() for expr in cast_exprs]
        for c in cols_to_cast:
            _reject_alias_collision(
                f"__pre_null__{c}", current_dtypes.names(), self.name, f"the pre-null snapshot for column '{c}'"
            )
            _reject_alias_collision(
                f"__coercion_ok__{c}", current_dtypes.names(), self.name, f"the coercion mask for column '{c}'"
            )
        pre_null_exprs = [pl.col(c).is_null().alias(f"__pre_null__{c}") for c in cols_to_cast]
        context.internal_columns.update(f"__pre_null__{c}" for c in cols_to_cast)
        context.data = lf.with_columns(pre_null_exprs).with_columns(cast_exprs)

        # True = no coercion failure; feeds check_masks like a real check.
        coercion_ok_exprs = [
            (~(pl.col(c).is_null() & ~pl.col(f"__pre_null__{c}"))).alias(f"__coercion_ok__{c}") for c in cols_to_cast
        ]
        context.data = context.data.with_columns(coercion_ok_exprs)
        context.internal_columns.update(f"__coercion_ok__{c}" for c in cols_to_cast)
        context.check_masks.update({(c, COERCION_CHECK): f"__coercion_ok__{c}" for c in cols_to_cast})

        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no column needs coercion.

        Args:
            context: Pipeline context.

        Returns:
            True if no column will be coerced.
        """
        return not any(context.schema.resolve_coerce(col_name) for col_name in context.schema.columns)


class FrameCheckPhase(PipelinePhase):
    """Apply frame-level checks (whole-DataFrame validations).

    Runs after coercion so frame checks see typed data, and before column
    checks. A ``FrameCheck`` always preserves rows and columns (enforced by
    the base class), so it can only pass a frame through or raise.

    Dependencies: coercion
    """

    def __init__(self) -> None:
        """Initialize frame check phase."""
        super().__init__(
            name="frame_checks",
            phase_type=PhaseType.CHECKING,
            dependencies=["coercion"],
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Apply frame checks in schema-declared order.

        Args:
            context: Pipeline context.

        Returns:
            Updated context with the frame checks applied.

        Raises:
            PipelineError: If a frame check is unregistered or fails.
        """
        registry = context.registry
        lf = context.data

        for check_spec in context.schema.frame_checks:
            try:
                check = registry.frame_checks.get(check_spec.name)
            except KeyError as e:
                raise PipelineError(
                    f"Frame check '{check_spec.name}' not found in registry. "
                    f"Available: {registry.frame_checks.list_names()}",
                    phase=self.name,
                ) from e

            try:
                lf = check(lf, **check_spec.args)
            except Exception as e:
                raise PipelineError(
                    f"Frame check '{check_spec.name}' failed: {e}",
                    phase=self.name,
                ) from e

        context.data = lf
        return context

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if the schema defines no frame checks.

        Args:
            context: Pipeline context.

        Returns:
            True if no frame checks are defined.
        """
        return not context.schema.frame_checks


class ColumnCheckPhase(PipelinePhase):
    """Apply column checks (validations).

    This phase applies all column-level checks defined in the schema,
    collecting validation errors for the error report.

    Dependencies: coercion (checks run on typed data)
    """

    def __init__(self) -> None:
        """Initialize column check phase."""
        super().__init__(
            name="column_checks",
            phase_type=PhaseType.CHECKING,
            dependencies=["coercion"],
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
        current_columns = lf.collect_schema().names()

        # Build boolean mask columns for each check (True = passed)
        # No collect here — downstream phases use these masks lazily
        mask_exprs: list[pl.Expr] = []
        # Preserve entries earlier phases (e.g. CoercionPhase) already registered.
        check_masks: dict[tuple[str, str], str] = dict(context.check_masks)
        notnull_aliases = self._build_notnull_mask_exprs(schema, current_columns, mask_exprs)
        # Independent of check_masks' size, so seeded coercion entries don't shift aliases.
        check_index = 0

        for col_name, col_schema in schema.columns.items():
            checks_to_run = list(col_schema.checks) if col_schema.checks else []

            if not checks_to_run:
                continue

            for check_spec in checks_to_run:
                if check_spec.name == COERCION_CHECK and schema.resolve_coerce(col_name):
                    raise PipelineError(
                        f"Column '{col_name}' has coercion enabled and also has a check named "
                        f"'{COERCION_CHECK}'. The name is reserved for the built-in coercion "
                        f"failure tracking. Rename the check.",
                        phase=self.name,
                    )

                try:
                    check = registry.column_checks.get(check_spec.name)
                except KeyError as e:
                    raise PipelineError(
                        f"Check '{check_spec.name}' not found in registry. "
                        f"Available: {registry.column_checks.list_names()}",
                        phase=self.name,
                    ) from e

                args = check_spec.args or {}
                try:
                    check_expr = check(pl.col(col_name), **args)
                except Exception as e:
                    raise PipelineError(
                        f"Failed to apply check '{check_spec.name}' to column '{col_name}': {e}",
                        phase=self.name,
                    ) from e

                # Index, not "{col}__{check}": the latter is ambiguous, since a column named
                # 'a__b' with check 'c' and a column 'a' with check 'b__c' both produce
                # '__check__a__b__c'. Nothing parses these aliases; they are opaque handles.
                alias = f"__check__{check_index}"
                check_index += 1
                _reject_alias_collision(
                    alias,
                    current_columns,
                    self.name,
                    f"the mask for check '{check_spec.name}' on column '{col_name}'",
                )
                mask_exprs.append(check_expr.alias(alias))
                check_masks[(col_name, check_spec.name)] = alias

        if mask_exprs:
            context.data = lf.with_columns(mask_exprs)
            context.internal_columns.update(e.meta.output_name() for e in mask_exprs)

        # Register the not-null masks as checks so they appear in the error report.
        # Without this, on_failure='ignore' would swallow the null entirely.
        for col_name, alias in notnull_aliases.items():
            key = (col_name, NOT_NULL_CHECK)
            if key in check_masks:
                raise PipelineError(
                    f"Column '{col_name}' is nullable=False and also has a check named "
                    f"'{NOT_NULL_CHECK}'. The name is reserved for the built-in not-null "
                    f"constraint. Rename the check.",
                    phase=self.name,
                )
            check_masks[key] = alias

        context.check_masks = check_masks

        self._enforce_notnull(context, notnull_aliases)

        return context

    @staticmethod
    def _build_notnull_mask_exprs(
        schema: SchemaModel,
        current_columns: list[str],
        mask_exprs: list[pl.Expr],
    ) -> dict[str, str]:
        """Add a not-null mask expression for every nullable=False column present in the data.

        Args:
            schema: Schema being validated.
            current_columns: Column names currently present in the data.
            mask_exprs: Mutable list of mask expressions to append to.

        Returns:
            Mapping of column name to its not-null mask alias.
        """
        notnull_aliases: dict[str, str] = {}
        for col_name, col_schema in schema.columns.items():
            if col_name not in current_columns:
                continue
            if col_schema.nullable is False:
                alias = f"__notnull__{col_name}"
                _reject_alias_collision(
                    alias, current_columns, "column_checks", f"the not-null mask for column '{col_name}'"
                )
                mask_exprs.append(pl.col(col_name).is_not_null().alias(alias))
                notnull_aliases[col_name] = alias
        return notnull_aliases

    def _enforce_notnull(self, context: PipelineContext, notnull_aliases: dict[str, str]) -> None:
        """Raise if any nullable=False column contains a null value, unless on_failure='ignore'.

        Args:
            context: Pipeline context with the not-null mask columns applied.
            notnull_aliases: Mapping of column name to its not-null mask alias.

        Raises:
            PipelineError: If a nullable=False column contains a null value and its
                resolved on_failure behavior is not 'ignore'.
        """
        if not notnull_aliases:
            return

        # Aggregate first: collects a single row, not one boolean per input row.
        notnull_check = context.data.select(
            [pl.col(alias).all().alias(alias) for alias in notnull_aliases.values()]
        ).collect()
        for col_name, alias in notnull_aliases.items():
            if not notnull_check[alias].item() and context.schema.resolve_on_failure(col_name) != "ignore":
                raise PipelineError(
                    f"Column '{col_name}' has nullable=False but contains null values.",
                    phase=self.name,
                )

    def can_skip(self, context: PipelineContext) -> bool:
        """Skip if no checks are defined in schema.

        Args:
            context: Pipeline context.

        Returns:
            True if no columns have checks defined.
        """
        return not any(col_schema.checks or not col_schema.nullable for col_schema in context.schema.columns.values())
