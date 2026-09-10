"""Type aliases shared across the package.

These name vocabulary that both `nyctea.schema` and `nyctea.engine` need. They
live here, at a leaf below both, so that neither package has to import the other
to say what a value is. See `tests/test_import_structure.py` for the layering
rule this serves.
"""

from typing import Literal

__all__ = ["AggregateEngine", "OnFailureBehavior"]

# How a validator failure is handled: raise, replace the value with null, or
# record the failure and leave the value alone.
OnFailureBehavior = Literal["raise", "null", "ignore"]

# The Polars engine used by validation's internal aggregate collects. Chosen once
# per validate() call from the data's size, see `SchemaModel.streaming_row_threshold`.
AggregateEngine = Literal["in-memory", "streaming"]
