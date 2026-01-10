"""Nyctea: Polars-based data validation library.

Nyctea provides a declarative schema-based validation system for Polars DataFrames
with an extensible plugin architecture.

Quick Start:
    >>> from nyctea.schema.model import SchemaModel
    >>> from nyctea.plugins.registry import MasterRegistry
    >>> from nyctea.plugins.builtins.register import register_builtins
    >>>
    >>> # Load schema and register plugins
    >>> schema = SchemaModel.from_yaml("schema.yaml")
    >>> registry = MasterRegistry()
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
from nyctea.schema.model import SchemaModel
from nyctea.plugins.registry import MasterRegistry
from nyctea.plugins.builtins.register import register_builtins, register_titanic_plugins
from nyctea.engine.validate import ValidationResult, ValidationReport, ErrorReportConfig
from nyctea.exceptions import (
    NycteaError,
    ValidationError,
    PluginError,
    PipelineError,
)

__all__ = [
    # Logging
    "configure_logging",
    # Schema and validation
    "SchemaModel",
    "ValidationResult",
    "ValidationReport",
    "ErrorReportConfig",
    # Plugin system
    "MasterRegistry",
    "register_builtins",
    "register_titanic_plugins",
    # Exceptions
    "NycteaError",
    "ValidationError",
    "PluginError",
    "PipelineError",
]
