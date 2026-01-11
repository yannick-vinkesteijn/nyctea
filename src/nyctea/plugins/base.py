"""Base plugin classes and metadata for Nyctea extensibility.

This module defines the foundation of Nyctea's plugin system, providing abstract
base classes that all plugins must inherit from and metadata structures for
plugin registration and discovery.
"""


from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

__all__ = [
    "PluginMetadata",
    "BasePlugin",
    "TInput",
    "TOutput",
]

# Generic type variables for plugin input/output
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


@dataclass(frozen=True)
class PluginMetadata:
    """Metadata describing a plugin.

    This immutable dataclass contains descriptive information about a plugin
    that is used for registration, discovery, and documentation generation.

    Attributes:
        name: Unique identifier for the plugin. Used for lookup in registries.
        description: Human-readable description of what the plugin does.
        version: Plugin version string (semantic versioning recommended).
        tags: Optional tags for categorization and discovery.
        author: Plugin author name or organization.
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    tags: Sequence[str] = field(default_factory=list)
    author: str = ""

    def __post_init__(self) -> None:
        """Validate metadata after initialization."""
        if not self.name:
            raise ValueError("Plugin name cannot be empty")
        if not self.name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"Plugin name '{self.name}' must be alphanumeric "
                "(underscores and hyphens allowed)"
            )


class BasePlugin(ABC, Generic[TInput, TOutput]):
    """Abstract base class for all Nyctea plugins.

    This class establishes the fundamental contract that all plugins must implement:
    - Metadata for registration and discovery
    - Execute method for core functionality
    - Argument validation
    - Optional call wrapper for additional runtime checks

    Type Parameters:
        TInput: The input type that the plugin accepts.
        TOutput: The output type that the plugin returns.

    Attributes:
        metadata: Plugin metadata including name, description, and tags.
    """

    def __init__(self, metadata: PluginMetadata) -> None:
        """Initialize the plugin with metadata.

        Args:
            metadata: Plugin metadata including name and description.
        """
        self.metadata = metadata

    @property
    def name(self) -> str:
        """Get the plugin name from metadata."""
        return self.metadata.name

    @abstractmethod
    def execute(self, input_data: TInput, **kwargs: Any) -> TOutput:
        """Execute the plugin's core functionality.

        This is the main entry point for plugin logic. Subclasses must implement
        this method to define what the plugin actually does.

        Args:
            input_data: The input to process.
            **kwargs: Additional plugin-specific arguments.

        Returns:
            The plugin's output.

        Raises:
            PluginExecutionError: If execution fails.
        """
        pass

    @abstractmethod
    def validate_args(self, **kwargs: Any) -> None:
        """Validate plugin arguments before execution.

        This method is called before execute() to ensure all arguments are
        valid and compatible with the plugin's requirements.

        Args:
            **kwargs: Arguments to validate.

        Raises:
            TypeError: If argument types are invalid.
            ValueError: If argument values are invalid.
        """
        pass

    def __call__(self, input_data: TInput, **kwargs: Any) -> TOutput:
        """Call the plugin with runtime validation.

        This wrapper method provides a hook for subclasses to add additional
        validation beyond argument checking (e.g., purity checks for column
        plugins, shape checks for frame plugins).

        The default implementation simply validates args and delegates to execute().
        Subclasses can override this to add custom validation.

        Args:
            input_data: The input to process.
            **kwargs: Additional plugin-specific arguments.

        Returns:
            The plugin's output.

        Raises:
            PluginExecutionError: If validation or execution fails.
        """
        # Validate arguments first
        self.validate_args(**kwargs)

        # Execute the plugin
        return self.execute(input_data, **kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the plugin."""
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"version='{self.metadata.version}')"
        )
