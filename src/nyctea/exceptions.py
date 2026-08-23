"""Exception hierarchy for Nyctea validation library.

This module defines a comprehensive exception hierarchy for all error conditions
that can occur during schema validation, validator registration, and pipeline execution.
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
    """Base exception for validator-related errors."""

    def __init__(
        self,
        message: str,
        *,
        validator_name: str | None = None,
        validator_type: str | None = None,
    ) -> None:
        """Initialize validator error with context.

        Args:
            message: Error description.
            validator_name: Name of the validator that caused the error.
            validator_type: Type of validator (e.g., "ColumnParser", "FrameCheck").
        """
        super().__init__(message)
        self.validator_name = validator_name
        self.validator_type = validator_type


class RegistrationError(ValidatorError):
    """Raised when validator registration fails.

    This occurs when:
    - A validator with the same name is already registered
    - Validator validation fails (invalid signature, missing methods, etc.)
    - Validator metadata is invalid
    """


class ValidatorExecutionError(ValidatorError):
    """Raised when validator execution fails.

    This occurs when:
    - Validator execute() method raises an exception
    - Validator violates purity constraints (column validators)
    - Validator violates shape constraints (frame validators)
    - Validator arguments are invalid
    """

    def __init__(
        self,
        message: str,
        *,
        validator_name: str | None = None,
        validator_type: str | None = None,
        column: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize validator execution error with context.

        Args:
            message: Error description.
            validator_name: Name of the validator that failed.
            validator_type: Type of validator.
            column: Column name (for column validators).
            original_error: The underlying exception that caused this error.
        """
        super().__init__(message, validator_name=validator_name, validator_type=validator_type)
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
