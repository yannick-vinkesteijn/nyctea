"""Nyctea: Polars-based data validation library.

Nyctea provides a declarative schema-based validation system for Polars DataFrames
with an extensible plugin architecture.

Quick Start:
    >>> from nyctea.schema.model import SchemaModel
    >>> from nyctea.plugins.registry import Registry
    >>> from nyctea.plugins.builtins.register import register_builtins
    >>>
    >>> # Load schema and register validators
    >>> schema = SchemaModel.from_yaml("schema.yaml")
    >>> registry = Registry()
    >>> register_builtins(registry)
    >>>
    >>> # Validate data
    >>> result = schema.run(df, registry)
    >>> print(result.report.summary())
"""

from nyctea.utils import configure_logging

# Configure logging on import
configure_logging()

# Core API exports
from nyctea.engine.validate import ErrorReportConfig, ValidationReport, ValidationResult
from nyctea.exceptions import (
    NycteaError,
    PipelineError,
    ValidationError,
    ValidatorError,
)
from nyctea.plugins.builtins.register import register_builtins, register_titanic_plugins
from nyctea.plugins.registry import Registry
from nyctea.schema.model import SchemaModel

__all__ = [
    "ErrorReportConfig",
    "NycteaError",
    "PipelineError",
    "Registry",
    "SchemaModel",
    "ValidationError",
    "ValidationReport",
    "ValidationResult",
    "ValidatorError",
    "configure_logging",
    "register_builtins",
    "register_titanic_plugins",
]


def __getattr__(name: str) -> object:
    if name == "FunctionRegistry":
        import warnings

        warnings.warn(
            "FunctionRegistry was renamed to Registry in v0.2.0. FunctionRegistry will be removed in v0.3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return Registry
    raise AttributeError(f"module 'nyctea' has no attribute {name!r}")
