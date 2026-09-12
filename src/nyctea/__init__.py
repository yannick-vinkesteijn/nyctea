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

import logging

from nyctea.utils import configure_logging

# A library emits records and lets the application decide handlers, levels and format.
# The null handler keeps `logging` quiet about a namespace nobody has configured.
# Guarded because a reload would otherwise stack a second one on the same logger.
_package_logger = logging.getLogger("nyctea")
if not any(isinstance(h, logging.NullHandler) for h in _package_logger.handlers):
    _package_logger.addHandler(logging.NullHandler())

# Core API exports
from nyctea.config import Config
from nyctea.engine.results import ErrorReportConfig, ValidationReport, ValidationResult
from nyctea.exceptions import (
    ConfigurationError,
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
    "Config",
    "ConfigurationError",
    "ErrorReportConfig",
    "NycteaError",
    "PipelineError",
    "Registry",
    "SchemaModel",
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
