"""The check names a run reports failures under.

Separate from the phases that register them, so the validator, the mask index and
the reporting module can name a failure kind without importing the pipeline.
"""

__all__ = ["COERCION_CHECK", "NOT_NULL_CHECK", "PARSING_CHECK"]

NOT_NULL_CHECK = "not_null"
"""Check name reported for a nullable=False column that contains nulls. Frozen, see test_phases.py."""

COERCION_CHECK = "coerce"
"""Check name reported for a failed dtype cast. Frozen, see test_phases.py."""

PARSING_CHECK = "parse"
"""Check name reported when a parser turns a non-null value into null."""
