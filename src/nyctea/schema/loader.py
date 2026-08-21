"""Utilities to load SchemaModel definitions from files or mappings."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nyctea.schema.model import SchemaModel

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


class SchemaLoader:
    """Loads SchemaModel definitions from JSON, YAML, or Python mappings."""

    def __init__(self, model_cls: type[SchemaModel] = SchemaModel) -> None:
        """Initialize loader with a schema model class.

        Args:
            model_cls: The schema model class to instantiate. Defaults to SchemaModel.
        """
        self.model_cls = model_cls

    def from_mapping(self, data: Mapping[str, Any]) -> SchemaModel:
        """Load a schema from a plain mapping.

        Args:
            data: Mapping representation of a schema.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ValueError: If validation fails.
        """
        try:
            return self.model_cls.model_validate(data)
        except ValidationError as err:
            raise ValueError(f"Invalid schema configuration: {err}") from err

    def from_python(self, schema: SchemaModel | Mapping[str, Any]) -> SchemaModel:
        """Accept an existing SchemaModel or a mapping defining one.

        Args:
            schema: Schema model instance or mapping.

        Returns:
            SchemaModel: Parsed or passed-through schema.
        """
        if isinstance(schema, self.model_cls):
            return schema
        return self.from_mapping(schema)  # type: ignore[arg-type]

    def from_json_str(self, content: str) -> SchemaModel:
        """Load a schema from a JSON string.

        Args:
            content: JSON text.

        Returns:
            SchemaModel: Parsed schema model.
        """
        return self.from_mapping(json.loads(content))

    def from_json_file(self, path: str | Path) -> SchemaModel:
        """Load a schema from a JSON file.

        Args:
            path: Path to JSON schema file.

        Returns:
            SchemaModel: Parsed schema model.
        """
        text = Path(path).read_text()
        return self.from_json_str(text)

    def from_yaml_str(self, content: str) -> SchemaModel:
        """Load a schema from a YAML string.

        Args:
            content: YAML text.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ImportError: If PyYAML is not installed.
        """
        self._ensure_yaml()
        assert yaml is not None  # for type checkers
        return self.from_mapping(yaml.safe_load(content))

    def from_yaml_file(self, path: str | Path) -> SchemaModel:
        """Load a schema from a YAML file.

        Args:
            path: Path to YAML schema file.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ImportError: If PyYAML is not installed.
        """
        text = Path(path).read_text()
        return self.from_yaml_str(text)

    @staticmethod
    def _ensure_yaml() -> None:
        """Raise if PyYAML is unavailable."""
        if yaml is None:
            raise ImportError("PyYAML is required for YAML schema loading. Install with `pip install pyyaml`.")


__all__ = ["SchemaLoader"]
