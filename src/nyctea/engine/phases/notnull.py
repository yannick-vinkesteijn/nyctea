"""Not-null masks for `nullable=False` columns.

Registered by the column check phase today. It lives here rather than inside that
phase because nullability is not itself a phase, and #87 has to be free to place it
somewhere else in the order.
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
) -> dict[str, str]:
    """Add a not-null mask expression for every nullable=False column present in the data.

    Args:
        schema: Schema being validated.
        phase: Name of the phase registering these masks, for the collision error.
            Passed in rather than hardcoded, so #87 can move the caller without the
            error attributing a failure to a phase that did not raise it.
        current_columns: Column names currently present in the data.
        occupied_columns: Input and schema column names unavailable to
            internal helpers.
        mask_exprs: Mutable list of mask expressions to append to.

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
        )
        mask_exprs.append(pl.col(col_name).is_not_null().alias(alias))
        notnull_aliases[col_name] = alias
    return notnull_aliases
