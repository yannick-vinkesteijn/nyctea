"""Type-safe validator registry system.

This module provides generic registry classes for managing validators with type safety,
metadata-based discovery, and lifecycle management.
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from nyctea.exceptions import RegistrationError
from nyctea.validators.base import Validator
from nyctea.validators.column import ColumnCheck, ColumnParser
from nyctea.validators.frame import FrameCheck, FrameParser

__all__ = [
    "Registry",
    "ValidatorRegistry",
]

T = TypeVar("T", bound=Validator)


class ValidatorRegistry(Generic[T]):
    """Type-safe registry for a specific validator type.

    This generic class manages a collection of validators of a single type,
    providing name-based lookup, tag-based discovery, and collision detection.

    Type Parameters:
        T: The validator type this registry manages (must extend Validator).

    Attributes:
        validator_type: The class of validators this registry accepts.
    """

    def __init__(self, validator_type: type[T]) -> None:
        """Initialize a validator registry for a specific type.

        Args:
            validator_type: The class of validators this registry will accept.
        """
        self.validator_type = validator_type
        self._validators: dict[str, T] = {}
        self._tags: dict[str, list[T]] = {}

    def register(self, validator: T) -> None:
        """Register a validator instance.

        Args:
            validator: The validator to register.

        Raises:
            TypeError: If validator is not of the correct type.
            RegistrationError: If a validator with the same name is already registered.
        """
        # Type validation
        if not isinstance(validator, self.validator_type):
            raise TypeError(f"Registry expects {self.validator_type.__name__}, got {type(validator).__name__}")

        # Name collision check
        if validator.name in self._validators:
            existing = self._validators[validator.name]
            raise RegistrationError(
                f"Validator '{validator.name}' is already registered as "
                f"{existing.__class__.__name__} (version {existing.metadata.version})",
                validator_name=validator.name,
                validator_type=self.validator_type.__name__,
            )

        # Register validator
        self._validators[validator.name] = validator

        # Index by tags
        for tag in validator.metadata.tags:
            if tag not in self._tags:
                self._tags[tag] = []
            self._tags[tag].append(validator)

    def get(self, name: str) -> T:
        """Get a validator by name.

        Args:
            name: Validator name to lookup.

        Returns:
            The validator instance.

        Raises:
            KeyError: If no validator with that name is registered.
        """
        if name not in self._validators:
            raise KeyError(
                f"No validator named '{name}' registered in "
                f"{self.validator_type.__name__} registry. "
                f"Available: {sorted(self._validators.keys())}"
            )
        return self._validators[name]

    def get_by_tag(self, tag: str) -> list[T]:
        """Get all validators with a specific tag.

        Args:
            tag: Tag to search for.

        Returns:
            List of validators with that tag (empty if none found).
        """
        return self._tags.get(tag, [])

    def list_all(self) -> list[T]:
        """Get all registered validators.

        Returns:
            List of all registered validators.
        """
        return list(self._validators.values())

    def list_names(self) -> list[str]:
        """Get names of all registered validators.

        Returns:
            Sorted list of validator names.
        """
        return sorted(self._validators.keys())

    def has(self, name: str) -> bool:
        """Check if a validator is registered.

        Args:
            name: Validator name to check.

        Returns:
            True if validator is registered, False otherwise.
        """
        return name in self._validators

    def __len__(self) -> int:
        """Get number of registered validators."""
        return len(self._validators)

    def __repr__(self) -> str:
        """Return string representation of registry."""
        return f"ValidatorRegistry[{self.validator_type.__name__}]({len(self._validators)} validators)"


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

    column_parsers: ValidatorRegistry[ColumnParser]
    column_checks: ValidatorRegistry[ColumnCheck]
    frame_parsers: ValidatorRegistry[FrameParser]
    frame_checks: ValidatorRegistry[FrameCheck]

    @model_validator(mode="before")
    @classmethod
    def _init_registries(cls, data: Any) -> Any:
        """Provide empty sub-registries when not supplied."""
        if not isinstance(data, dict):
            return data
        if "column_parsers" not in data:
            data["column_parsers"] = ValidatorRegistry(ColumnParser)
        if "column_checks" not in data:
            data["column_checks"] = ValidatorRegistry(ColumnCheck)
        if "frame_parsers" not in data:
            data["frame_parsers"] = ValidatorRegistry(FrameParser)
        if "frame_checks" not in data:
            data["frame_checks"] = ValidatorRegistry(FrameCheck)
        return data

    def register_column_parser(self, validator: ColumnParser) -> None:
        """Register a column parser validator.

        Args:
            validator: Column parser to register.
        """
        self.column_parsers.register(validator)

    def register_column_check(self, validator: ColumnCheck) -> None:
        """Register a column check validator.

        Args:
            validator: Column check to register.
        """
        self.column_checks.register(validator)

    def register_frame_parser(self, validator: FrameParser) -> None:
        """Register a frame parser validator.

        Args:
            validator: Frame parser to register.
        """
        self.frame_parsers.register(validator)

    def register_frame_check(self, validator: FrameCheck) -> None:
        """Register a frame check validator.

        Args:
            validator: Frame check to register.
        """
        self.frame_checks.register(validator)

    def get_validator_counts(self) -> dict[str, int]:
        """Get count of validators in each registry.

        Returns:
            Dictionary mapping registry name to validator count.
        """
        return {
            "column_parsers": len(self.column_parsers),
            "column_checks": len(self.column_checks),
            "frame_parsers": len(self.frame_parsers),
            "frame_checks": len(self.frame_checks),
        }

    def __repr__(self) -> str:
        """Return string representation of registry."""
        counts = self.get_validator_counts()
        return (
            f"Registry("
            f"column_parsers={counts['column_parsers']}, "
            f"column_checks={counts['column_checks']}, "
            f"frame_parsers={counts['frame_parsers']}, "
            f"frame_checks={counts['frame_checks']})"
        )
