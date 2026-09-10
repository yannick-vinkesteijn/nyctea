"""Helpers every phase needs when it generates an internal column."""

from collections.abc import Collection

from nyctea.engine.context import PipelineContext
from nyctea.exceptions import PipelineError
from nyctea.utils import occupied_columns

__all__ = ["reject_alias_collision", "reserved_columns"]


def reject_alias_collision(alias: str, occupied_columns: Collection[str], phase: str, what: str) -> None:
    """Raise if a generated internal column would overwrite a declared or input column.

    Args:
        alias: Generated internal column name.
        occupied_columns: Input or schema column names that cannot be overwritten.
        phase: Phase name, for the error.
        what: Human description of what the alias is for.

    Raises:
        PipelineError: If the alias collides with an existing column.
    """
    if alias in occupied_columns:
        raise PipelineError(
            f"Cannot build {what}: the data or schema already contains a column named "
            f"'{alias}'. Rename it before validating.",
            phase=phase,
        )


def reserved_columns(context: PipelineContext) -> set[str]:
    """Return every input and schema column name unavailable to internal helpers."""
    return occupied_columns(context.get_column_names(), context.schema.accepted_names)
