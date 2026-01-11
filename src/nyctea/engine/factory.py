"""Pipeline factory for creating preset validation pipelines.

This module provides factory functions for creating validation pipelines
with common configurations.
"""


from collections.abc import Sequence
from typing import TYPE_CHECKING

from nyctea.engine.phases import (
    ColumnCheckPhase,
    ColumnParsingPhase,
    ColumnResolutionPhase,
)
from nyctea.engine.pipeline import ValidationPipeline

if TYPE_CHECKING:
    from nyctea.engine.observability import PipelineObserver
    from nyctea.schema.model import SchemaModel

__all__ = [
    "create_minimal_pipeline",
    "create_pipeline_from_schema",
    "create_standard_pipeline",
]


def create_minimal_pipeline(
    observers: Sequence[PipelineObserver] | None = None,
) -> ValidationPipeline:
    """Create a minimal validation pipeline.

    This pipeline includes only the essential phases:
    - Column resolution
    - Column parsing
    - Column checks

    Args:
        observers: Optional pipeline observers.

    Returns:
        Configured validation pipeline.

    Example:
        >>> pipeline = create_minimal_pipeline()
        >>> result = pipeline.execute(context)
    """
    phases = [
        ColumnResolutionPhase(),
        ColumnParsingPhase(),
        ColumnCheckPhase(),
    ]

    return ValidationPipeline(phases=phases, observers=observers)


def create_standard_pipeline(
    observers: Sequence[PipelineObserver] | None = None,
) -> ValidationPipeline:
    """Create a standard validation pipeline.

    For now, this is the same as minimal. In the full implementation,
    this would include additional phases like coercion, error reporting, etc.

    Args:
        observers: Optional pipeline observers.

    Returns:
        Configured validation pipeline.

    Example:
        >>> pipeline = create_standard_pipeline()
        >>> result = pipeline.execute(context)
    """
    # For now, standard = minimal
    # TODO: Add coercion, error reporting, nullification phases
    return create_minimal_pipeline(observers=observers)


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

    # Add parsing phase if any column has parsers
    has_parsers = any(
        col_schema.parsers
        for col_schema in schema.columns.values()
    )
    if has_parsers:
        phases.append(ColumnParsingPhase())

    # Add check phase if any column has checks or nullable=False
    has_checks = any(
        col_schema.checks or not col_schema.nullable
        for col_schema in schema.columns.values()
    )
    if has_checks:
        phases.append(ColumnCheckPhase())

    return ValidationPipeline(phases=phases, observers=observers)
