"""Exception hierarchy for Nyctea validation library.

This module defines a comprehensive exception hierarchy for all error conditions
that can occur during schema validation, plugin registration, and pipeline execution.
"""

import polars as pl

__all__ = [
    "ConfigurationError",
    "NycteaError",
    "PipelineError",
    "RegistrationError",
    "ValidationError",
    "ValidatorError",
    "ValidatorExecutionError",
]


class NycteaError(Exception):
    """Base exception for all Nyctea errors.

    All custom exceptions in Nyctea inherit from this base class,
    making it easy to catch any library-specific error.
    """


class ValidatorError(NycteaError):
    """Base exception for plugin-related errors."""

    def __init__(
        self,
        message: str,
        *,
        plugin_name: str | None = None,
        plugin_type: str | None = None,
    ) -> None:
        """Initialize plugin error with context.

        Args:
            message: Error description.
            plugin_name: Name of the plugin that caused the error.
            plugin_type: Type of plugin (e.g., "ColumnParser", "FrameCheck").
        """
        super().__init__(message)
        self.plugin_name = plugin_name
        self.plugin_type = plugin_type


class RegistrationError(ValidatorError):
    """Raised when plugin registration fails.

    This occurs when:
    - A plugin with the same name is already registered
    - Plugin validation fails (invalid signature, missing methods, etc.)
    - Plugin metadata is invalid
    """


class ValidatorExecutionError(ValidatorError):
    """Raised when plugin execution fails.

    This occurs when:
    - Plugin execute() method raises an exception
    - Plugin violates purity constraints (column plugins)
    - Plugin violates shape constraints (frame plugins)
    - Plugin arguments are invalid
    """

    def __init__(
        self,
        message: str,
        *,
        plugin_name: str | None = None,
        plugin_type: str | None = None,
        column: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize plugin execution error with context.

        Args:
            message: Error description.
            plugin_name: Name of the plugin that failed.
            plugin_type: Type of plugin.
            column: Column name (for column plugins).
            original_error: The underlying exception that caused this error.
        """
        super().__init__(message, plugin_name=plugin_name, plugin_type=plugin_type)
        self.column = column
        self.original_error = original_error


class ValidationError(NycteaError):
    """Raised when data validation fails.

    This occurs when:
    - Data fails schema validation in strict mode
    - Required columns are missing
    - Nullable constraints are violated
    - Type coercion fails in strict mode
    """

    def __init__(
        self,
        message: str,
        *,
        column: str | None = None,
        phase: str | None = None,
        errors: pl.DataFrame | None = None,
        error_count: int | None = None,
    ) -> None:
        """Initialize validation error with context.

        Args:
            message: Error description.
            column: Column name that failed validation (if applicable).
            phase: Pipeline phase where validation failed.
            errors: DataFrame containing validation errors.
            error_count: Number of validation errors.
        """
        super().__init__(message)
        self.column = column
        self.phase = phase
        self.errors = errors
        self.error_count = error_count


class PipelineError(NycteaError):
    """Raised when pipeline execution or configuration fails.

    This occurs when:
    - Phase dependencies are violated
    - Required phases are missing
    - Phase ordering is invalid
    - Phase execution fails
    """

    def __init__(
        self,
        message: str,
        *,
        phase: str | None = None,
        pipeline_state: str | None = None,
    ) -> None:
        """Initialize pipeline error with context.

        Args:
            message: Error description.
            phase: Name of the phase that caused the error.
            pipeline_state: Current state of the pipeline.
        """
        super().__init__(message)
        self.phase = phase
        self.pipeline_state = pipeline_state


class ConfigurationError(NycteaError):
    """Raised when configuration is invalid.

    This occurs when:
    - Schema definition is malformed
    - Configuration file is invalid
    - Environment variables are invalid
    - Runtime options conflict with schema
    """
