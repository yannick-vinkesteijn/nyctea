"""Type-safe plugin registry system.

This module provides generic registry classes for managing plugins with type safety,
metadata-based discovery, and lifecycle management.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from nyctea.exceptions import RegistrationError
from nyctea.plugins.base import Validator
from nyctea.plugins.column import ColumnCheck, ColumnParser
from nyctea.plugins.frame import FrameCheck, FrameParser

__all__ = [
    "PluginRegistry",
    "Registry",
]

T = TypeVar("T", bound=Validator)


class PluginRegistry(Generic[T]):
    """Type-safe registry for a specific plugin type.

    This generic class manages a collection of plugins of a single type,
    providing name-based lookup, tag-based discovery, and collision detection.

    Type Parameters:
        T: The plugin type this registry manages (must extend Validator).

    Attributes:
        plugin_type: The class of plugins this registry accepts.
    """

    def __init__(self, plugin_type: type[T]) -> None:
        """Initialize a plugin registry for a specific type.

        Args:
            plugin_type: The class of plugins this registry will accept.
        """
        self.plugin_type = plugin_type
        self._plugins: dict[str, T] = {}
        self._tags: dict[str, list[T]] = {}

    def register(self, plugin: T) -> None:
        """Register a plugin instance.

        Args:
            plugin: The plugin to register.

        Raises:
            TypeError: If plugin is not of the correct type.
            RegistrationError: If a plugin with the same name is already registered.
        """
        # Type validation
        if not isinstance(plugin, self.plugin_type):
            raise TypeError(f"Registry expects {self.plugin_type.__name__}, got {type(plugin).__name__}")

        # Name collision check
        if plugin.name in self._plugins:
            existing = self._plugins[plugin.name]
            raise RegistrationError(
                f"Plugin '{plugin.name}' is already registered as "
                f"{existing.__class__.__name__} (version {existing.metadata.version})",
                plugin_name=plugin.name,
                plugin_type=self.plugin_type.__name__,
            )

        # Register plugin
        self._plugins[plugin.name] = plugin

        # Index by tags
        for tag in plugin.metadata.tags:
            if tag not in self._tags:
                self._tags[tag] = []
            self._tags[tag].append(plugin)

    def get(self, name: str) -> T:
        """Get a plugin by name.

        Args:
            name: Plugin name to lookup.

        Returns:
            The plugin instance.

        Raises:
            KeyError: If no plugin with that name is registered.
        """
        if name not in self._plugins:
            raise KeyError(
                f"No plugin named '{name}' registered in "
                f"{self.plugin_type.__name__} registry. "
                f"Available: {sorted(self._plugins.keys())}"
            )
        return self._plugins[name]

    def get_by_tag(self, tag: str) -> list[T]:
        """Get all plugins with a specific tag.

        Args:
            tag: Tag to search for.

        Returns:
            List of plugins with that tag (empty if none found).
        """
        return self._tags.get(tag, [])

    def list_all(self) -> list[T]:
        """Get all registered plugins.

        Returns:
            List of all registered plugins.
        """
        return list(self._plugins.values())

    def list_names(self) -> list[str]:
        """Get names of all registered plugins.

        Returns:
            Sorted list of plugin names.
        """
        return sorted(self._plugins.keys())

    def has(self, name: str) -> bool:
        """Check if a plugin is registered.

        Args:
            name: Plugin name to check.

        Returns:
            True if plugin is registered, False otherwise.
        """
        return name in self._plugins

    def __len__(self) -> int:
        """Get number of registered plugins."""
        return len(self._plugins)

    def __repr__(self) -> str:
        """Return string representation of registry."""
        return f"PluginRegistry[{self.plugin_type.__name__}]({len(self._plugins)} plugins)"


class Registry(BaseModel):
    """Registry containing all validator types.

    This Pydantic model manages separate registries for each validator type,
    providing type-safe registration methods and centralized validator management.

    Attributes:
        column_parsers: Registry for column parser validators.
        column_checks: Registry for column check validators.
        frame_parsers: Registry for frame parser validators.
        frame_checks: Registry for frame check validators.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    column_parsers: PluginRegistry[ColumnParser]
    column_checks: PluginRegistry[ColumnCheck]
    frame_parsers: PluginRegistry[FrameParser]
    frame_checks: PluginRegistry[FrameCheck]

    @model_validator(mode="before")
    @classmethod
    def _init_registries(cls, data: Any) -> Any:
        """Provide empty sub-registries when not supplied."""
        if not isinstance(data, dict):
            return data
        if "column_parsers" not in data:
            data["column_parsers"] = PluginRegistry(ColumnParser)
        if "column_checks" not in data:
            data["column_checks"] = PluginRegistry(ColumnCheck)
        if "frame_parsers" not in data:
            data["frame_parsers"] = PluginRegistry(FrameParser)
        if "frame_checks" not in data:
            data["frame_checks"] = PluginRegistry(FrameCheck)
        return data

    def register_column_parser(self, plugin: ColumnParser) -> None:
        """Register a column parser plugin.

        Args:
            plugin: Column parser to register.
        """
        self.column_parsers.register(plugin)

    def register_column_check(self, plugin: ColumnCheck) -> None:
        """Register a column check plugin.

        Args:
            plugin: Column check to register.
        """
        self.column_checks.register(plugin)

    def register_frame_parser(self, plugin: FrameParser) -> None:
        """Register a frame parser plugin.

        Args:
            plugin: Frame parser to register.
        """
        self.frame_parsers.register(plugin)

    def register_frame_check(self, plugin: FrameCheck) -> None:
        """Register a frame check plugin.

        Args:
            plugin: Frame check to register.
        """
        self.frame_checks.register(plugin)

    def get_plugin_counts(self) -> dict[str, int]:
        """Get count of plugins in each registry.

        Returns:
            Dictionary mapping registry name to plugin count.
        """
        return {
            "column_parsers": len(self.column_parsers),
            "column_checks": len(self.column_checks),
            "frame_parsers": len(self.frame_parsers),
            "frame_checks": len(self.frame_checks),
        }

    def __repr__(self) -> str:
        """Return string representation of registry."""
        counts = self.get_plugin_counts()
        return (
            f"Registry("
            f"column_parsers={counts['column_parsers']}, "
            f"column_checks={counts['column_checks']}, "
            f"frame_parsers={counts['frame_parsers']}, "
            f"frame_checks={counts['frame_checks']})"
        )
