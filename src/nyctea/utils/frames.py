"""Column-name helpers shared by the engine."""

from collections.abc import Iterable

__all__ = ["occupied_columns"]


def occupied_columns(names: Iterable[str], reserved: Iterable[str]) -> set[str]:
    """Every name already taken, so a generated helper column can avoid them.

    Takes names rather than a frame so the caller can pass an already-resolved
    list. Resolving a LazyFrame's schema is the expensive half, and the engine
    caches it on ``PipelineContext.frame_schema()``.

    Args:
        names: Column names currently present in the data.
        reserved: Further names that are unavailable, such as the schema's
            accepted names, which a later phase may still rename a column to.

    Returns:
        The union of the two.
    """
    return set(names) | set(reserved)
