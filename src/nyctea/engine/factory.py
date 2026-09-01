"""Pipeline factory for creating preset validation pipelines.

This module provides factory functions for creating validation pipelines
with common configurations.
"""

from collections.abc import Sequence

from nyctea.engine.observability import PipelineObserver
from nyctea.engine.phases import (
    CoercionPhase,
    ColumnCheckPhase,
    ColumnParsingPhase,
    ColumnResolutionPhase,
    FrameCheckPhase,
    FrameParsingPhase,
)
from nyctea.engine.pipeline import ValidationPipeline
from nyctea.schema.model import SchemaModel

__all__ = [
    "create_pipeline_from_schema",
]


def create_pipeline_from_schema(
    schema: SchemaModel,
    observers: Sequence[PipelineObserver] | None = None,
) -> ValidationPipeline:
    """Create a pipeline optimized for a specific schema.

    This factory builds a pipeline with only the phases needed based on
    the schema definition. Phases are omitted if not required.

    Args:
        schema: Schema model to build pipeline for.
        observers: Optional pipeline observers.

    Returns:
        Configured validation pipeline.

    Example:
        >>> schema = SchemaModel.from_yaml("schema.yaml")
        >>> pipeline = create_pipeline_from_schema(schema)
        >>> result = pipeline.execute(context)
    """
    phases = []

    # Column resolution is always required
    phases.append(ColumnResolutionPhase())

    if schema.frame_parsers:
        phases.append(FrameParsingPhase())

    # Add parsing phase if any column has parsers
    has_parsers = any(col_schema.parsers for col_schema in schema.columns.values())
    if has_parsers:
        phases.append(ColumnParsingPhase())

    # Coercion always present (can_skip handles coerce=False)
    phases.append(CoercionPhase())

    if schema.frame_checks:
        phases.append(FrameCheckPhase())

    # Add check phase if any column has checks or nullable=False
    has_checks = any(col_schema.checks or not col_schema.nullable for col_schema in schema.columns.values())
    if has_checks:
        phases.append(ColumnCheckPhase())

    return ValidationPipeline(phases=phases, observers=observers)
