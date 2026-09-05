"""The mask aliases a run registers, indexed once for every consumer."""

from dataclasses import dataclass
from typing import TypeVar

from nyctea.engine.phases import COERCION_CHECK, NOT_NULL_CHECK, PARSING_CHECK
from nyctea.schema.model import SchemaModel

__all__ = ["MaskIndex", "index_masks", "resolving_to"]


_Aliases = TypeVar("_Aliases", str, list[str])


def resolving_to(columns: dict[str, _Aliases], schema: SchemaModel, on_failure: str) -> dict[str, _Aliases]:
    """The subset of ``columns`` whose resolved on_failure behaviour is ``on_failure``."""
    return {col: value for col, value in columns.items() if schema.resolve_on_failure(col) == on_failure}


@dataclass(frozen=True)
class MaskIndex:
    """``context.check_masks`` partitioned once, by kind and by column.

    ``entries`` is the flat view, ``(column, check, alias)`` in registration order.
    That order reaches the user, since it is the row order of the error report, so
    nothing derived from it may sort or otherwise reorder.

    ``declared`` holds user-declared checks only. Parser, coercion and built-in
    not-null failures are excluded because each has its own enforcement and report
    accounting. Their failed values are already null, so nulling them again through
    an ``on_failure='null'`` column would double-count them in ``nullified_counts``.
    The not-null check can never resolve to ``'null'`` in any case: it exists only
    for non-nullable columns, whose ``'null'`` behaviour resolves to ``'raise'``.
    """

    entries: tuple[tuple[str, str, str], ...]
    parsing: dict[str, str]
    coercion: dict[str, str]
    notnull: dict[str, str]
    declared: dict[str, list[str]]

    @property
    def all_aliases(self) -> list[str]:
        """Every mask alias, in registration order."""
        return [alias for _, _, alias in self.entries]

    @property
    def reported(self) -> dict[str, list[str]]:
        """Aliases behind the per-column ``check_failures`` stat.

        Wider than ``declared``, because that stat counts a not-null failure as a
        check failure.
        """
        grouped: dict[str, list[str]] = {}
        for column, check, alias in self.entries:
            if check not in (PARSING_CHECK, COERCION_CHECK):
                grouped.setdefault(column, []).append(alias)
        return grouped


def index_masks(check_masks: dict[tuple[str, str], str]) -> MaskIndex:
    """Partition the mask aliases in one pass over ``check_masks``."""
    entries: list[tuple[str, str, str]] = []
    parsing: dict[str, str] = {}
    coercion: dict[str, str] = {}
    notnull: dict[str, str] = {}
    declared: dict[str, list[str]] = {}
    for (col_name, check_name), alias in check_masks.items():
        entries.append((col_name, check_name, alias))
        if check_name == PARSING_CHECK:
            parsing[col_name] = alias
        elif check_name == COERCION_CHECK:
            coercion[col_name] = alias
        elif check_name == NOT_NULL_CHECK:
            notnull[col_name] = alias
        else:
            declared.setdefault(col_name, []).append(alias)
    return MaskIndex(tuple(entries), parsing, coercion, notnull, declared)
