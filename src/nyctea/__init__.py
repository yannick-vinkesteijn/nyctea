"""Nyctea: Polars-based data validation library.

Nyctea provides a declarative schema-based validation system for Polars DataFrames
with an extensible validator architecture.

Quick Start:
    >>> from nyctea import Registry, SchemaModel, register_builtins
    >>>
    >>> # Load schema and register validators
    >>> schema = SchemaModel.from_yaml("schema.yaml")
    >>> registry = Registry()
    >>> register_builtins(registry)
    >>>
    >>> # Validate data
    >>> result = schema.validate(df, registry)
    >>> print(result.report.summary())
"""

from nyctea.utils import configure_logging

# Configure logging on import
configure_logging()

# Core API exports
from nyctea.engine.results import ErrorReportConfig, ValidationReport, ValidationResult
from nyctea.engine.validator import DataValidator
from nyctea.exceptions import (
    NycteaError,
    PipelineError,
    ValidationError,
    ValidatorError,
)
from nyctea.schema.model import SchemaModel
from nyctea.validators.builtins.register import register_builtins
from nyctea.validators.decorators import checker, frame_checker, frame_parser, parser
from nyctea.validators.registry import Registry

__all__ = [
    "ErrorReportConfig",
    "NycteaError",
    "PipelineError",
    "Registry",
    "SchemaModel",
    "DataValidator",
    "ValidationError",
    "ValidationReport",
    "ValidationResult",
    "checker",
    "frame_checker",
    "frame_parser",
    "parser",
    "ValidatorError",
    "configure_logging",
    "register_builtins",
]
