"""Not-null masks for `nullable=False` columns.

Built separately from declared checks because nullability is a generated postcondition.
`NotNullPhase` registers these masks last, after every phase that can introduce nulls.
"""

from collections.abc import Collection

import polars as pl

from nyctea.engine.phases.common import reject_alias_collision
from nyctea.schema.model import SchemaModel

__all__ = ["build_notnull_mask_exprs"]


def build_notnull_mask_exprs(
    schema: SchemaModel,
    phase: str,
    current_columns: Collection[str],
    occupied_columns: Collection[str],
    mask_exprs: list[pl.Expr],
    declared_check_aliases: dict[str, list[str]],
) -> dict[str, str]:
    """Add a not-null mask expression for every nullable=False column present in the data.

    An on_failure='null' column's failing checks are nulled later by
    ``apply_check_null``, after this phase runs, so the mask folds in the same
    failure expression to predict that outcome instead of missing it.

    Args:
        schema: Schema being validated.
        phase: Name of the phase registering these masks, for the collision error.
            Passed in rather than hardcoded, so a different caller's error still
            attributes to the phase that actually raised it.
        current_columns: Column names currently present in the data.
        occupied_columns: Input and schema column names unavailable to
            internal helpers.
        mask_exprs: Mutable list of mask expressions to append to.
        declared_check_aliases: Column name to its declared-check mask aliases
            (``MaskIndex.declared``).

    Returns:
        Mapping of column name to its not-null mask alias.
    """
    notnull_aliases: dict[str, str] = {}
    for col_name in schema.non_nullable_columns:
        if col_name not in current_columns:
            continue
        alias = f"__notnull__{col_name}"
        reject_alias_collision(
            alias,
            occupied_columns,
            phase,
            f"the not-null mask for column '{col_name}'",
            col_name,
        )
        not_null_expr = pl.col(col_name).is_not_null()
        check_aliases = declared_check_aliases.get(col_name)
        if check_aliases and schema.resolve_on_failure(col_name) == "null":
            about_to_be_nulled = pl.any_horizontal([~pl.col(a) for a in check_aliases])
            not_null_expr = not_null_expr & ~about_to_be_nulled
        mask_exprs.append(not_null_expr.alias(alias))
        notnull_aliases[col_name] = alias
    return notnull_aliases
