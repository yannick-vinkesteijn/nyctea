"""Exception hierarchy for Nyctea validation library."""

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
    """Base exception for all Nyctea errors."""


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
    """Raised when validator registration fails: name collision or invalid signature."""


class ValidatorExecutionError(ValidatorError):
    """Raised when validator execution fails, or violates a purity/shape constraint."""

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
    """Raised when the input does not have the structure the schema describes.

    Column resolution raises it when a required column is missing from the input or a
    name resolves ambiguously. A custom phase may raise it for a structural problem of
    its own, and the pipeline passes it to the caller unwrapped.
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
    """Raised when pipeline construction, ordering, or phase execution fails."""

    def __init__(
        self,
        message: str,
        *,
        phase: str | None = None,
        pipeline_state: str | None = None,
        column: str | None = None,
    ) -> None:
        """Initialize pipeline error with context.

        Args:
            message: Error description.
            phase: Name of the phase that caused the error.
            pipeline_state: Current state of the pipeline.
            column: Column whose failure triggered the error, when one column owns it.
        """
        super().__init__(message)
        self.phase = phase
        self.pipeline_state = pipeline_state
        self.column = column


class ConfigurationError(NycteaError):
    """Raised when a schema does not verify against a registry."""
