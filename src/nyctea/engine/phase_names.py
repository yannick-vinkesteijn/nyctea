"""The name of every built-in phase, defined once.

Read by the phase itself, by the `dependencies` of phases ordered against it, and by
the raise plan that attributes a failure.
"""

COLUMN_RESOLUTION_PHASE = "column_resolution"
FRAME_PARSING_PHASE = "frame_parsing"
COLUMN_PARSING_PHASE = "column_parsing"
COERCION_PHASE = "coercion"
FRAME_CHECKS_PHASE = "frame_checks"
COLUMN_CHECKS_PHASE = "column_checks"
NOT_NULL_PHASE = "not_null"

__all__ = [
    "COERCION_PHASE",
    "COLUMN_CHECKS_PHASE",
    "COLUMN_PARSING_PHASE",
    "COLUMN_RESOLUTION_PHASE",
    "FRAME_CHECKS_PHASE",
    "FRAME_PARSING_PHASE",
    "NOT_NULL_PHASE",
]
