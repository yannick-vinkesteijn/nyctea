"""Base validator classes and metadata for Nyctea extensibility."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

__all__ = [
    "TInput",
    "TOutput",
    "Validator",
    "ValidatorMetadata",
]

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


@dataclass(frozen=True)
class ValidatorMetadata:
    """Metadata describing a validator.

    Attributes:
        name: Unique identifier for the validator. Used for lookup in registries.
        description: Human-readable description of what the validator does.
        version: Validator version string (semantic versioning recommended).
        tags: Optional tags for categorization and discovery.
        author: Validator author name or organization.
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    tags: Sequence[str] = field(default_factory=list)
    author: str = ""

    def __post_init__(self) -> None:
        """Validate metadata after initialization."""
        if not self.name:
            raise ValueError("Validator name cannot be empty")
        if not self.name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Validator name '{self.name}' must be alphanumeric (underscores and hyphens allowed)")


class Validator(ABC, Generic[TInput, TOutput]):
    """Abstract base class for all Nyctea validators.

    Attributes:
        metadata: Validator metadata including name, description, and tags.
    """

    def __init__(self, metadata: ValidatorMetadata) -> None:
        """Initialize the validator with metadata.

        Args:
            metadata: Validator metadata including name and description.
        """
        self.metadata = metadata

    @property
    def name(self) -> str:
        """Get the validator name from metadata."""
        return self.metadata.name

    @abstractmethod
    def execute(self, input_data: TInput, **kwargs: Any) -> TOutput:
        """Execute the validator's core functionality.

        Args:
            input_data: The input to process.
            **kwargs: Additional validator-specific arguments.

        Returns:
            The validator's output.

        Raises:
            ValidatorExecutionError: If execution fails.
        """

    @abstractmethod
    def validate_args(self, **kwargs: Any) -> None:
        """Validate validator arguments before execution.

        Args:
            **kwargs: Arguments to validate.

        Raises:
            TypeError: If argument types are invalid.
            ValueError: If argument values are invalid.
        """

    def __call__(self, input_data: TInput, **kwargs: Any) -> TOutput:
        """Call the validator with runtime validation.

        Subclasses can override this to add checks beyond argument validation,
        e.g. purity checks for column validators, shape checks for frame validators.

        Args:
            input_data: The input to process.
            **kwargs: Additional validator-specific arguments.

        Returns:
            The validator's output.

        Raises:
            ValidatorExecutionError: If validation or execution fails.
        """
        self.validate_args(**kwargs)
        return self.execute(input_data, **kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the validator."""
        return f"{self.__class__.__name__}(name='{self.name}', version='{self.metadata.version}')"
