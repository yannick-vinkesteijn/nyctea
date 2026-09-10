"""The check names a run reports failures under.

Separate from the phases that register them, so the validator, the mask index and
the reporting module can name a failure kind without importing the pipeline.
"""

__all__ = ["COERCION_CHECK", "NOT_NULL_CHECK", "PARSING_CHECK", "STRUCTURAL_CHECKS", "category_of"]

NOT_NULL_CHECK = "not_null"
"""Check name reported for a nullable=False column that contains nulls. Frozen, see test_phases.py."""

COERCION_CHECK = "coerce"
"""Check name reported for a failed dtype cast. Frozen, see test_phases.py."""

PARSING_CHECK = "parse"
"""Check name reported when a parser turns a non-null value into null."""


STRUCTURAL_CHECKS = frozenset({NOT_NULL_CHECK, COERCION_CHECK, PARSING_CHECK})
"""Failures about the shape of the data rather than a rule the author wrote.

A value that will not cast, or a null in a non-nullable column, is a precondition the
data did not meet. A failing `min_value` is a business rule it did not satisfy. Callers
had to know that `check in (...)` meant the first kind; the category says it (#33).
"""


def category_of(check_name: str) -> str:
    """Which kind of failure a check name reports.

    Args:
        check_name: The name a failure is reported under.

    Returns:
        ``"structural"`` for a dtype, coercion or nullability failure, else ``"check"``.
    """
    return "structural" if check_name in STRUCTURAL_CHECKS else "check"
