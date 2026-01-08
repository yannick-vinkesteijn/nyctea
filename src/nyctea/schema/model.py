"""Pydantic models describing the validation schema.

This module provides Pydantic models for defining data validation schemas. Schemas
can be defined programmatically or loaded from YAML/JSON files.

The schema defines:
    - Column specifications (dtypes, nullability, parsers, checks)
    - Frame-level operations (parsers and checks)
    - Validation profiles (strict, clean, audit)
    - Synonym mappings for column names

Example:
    Basic schema definition::

        from nyctea.schema.model import SchemaModel

        schema = SchemaModel.from_dict({
            "columns": {
                "age": {
                    "dtype": "Int64",
                    "nullable": False,
                    "checks": [{"name": "positive"}]
                }
            }
        })

    Load from YAML::

        schema = SchemaModel.from_yaml_file("schema.yaml")

Note:
    All schemas are validated at creation time to ensure consistency
    (e.g., `nullable=False` cannot be combined with `on_failure="null"`).
"""


import json
from pathlib import Path
from typing import Any, Literal
from collections.abc import Mapping

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# Type aliases for validation behavior
OnFailureBehavior = Literal["raise", "null"]
ValidationProfile = Literal["strict", "clean", "audit"]

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


class Parser(BaseModel):
    """Configuration for a column-level parser."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Name of the parse function to apply")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the parse function"
    )


class Check(BaseModel):
    """Configuration for a column-level check."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Name of the check function to apply")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the check function"
    )


class FrameParser(BaseModel):
    """Configuration for a frame-level parser."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Name of the frame-level parser to apply")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the frame parser"
    )


class FrameCheck(BaseModel):
    """Configuration for a frame-level check."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Name of the frame-level check to apply")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the frame check"
    )


class ColumnSchema(BaseModel):
    """Schema for a single column."""

    model_config = ConfigDict(extra="forbid")

    dtype: str = Field(..., description="The final enforced dtype after validation")
    synonyms: list[str] = Field(
        default_factory=list, description="Allowed alternative names for this column"
    )

    parsers: list[Parser] = Field(
        default_factory=list,
        description="List of parser functions applied before checking",
    )

    checks: list[Check] = Field(
        default_factory=list,
        description="List of checks applied independently on the parsed column",
    )

    required: bool = Field(
        True,
        description="Whether this column must be present in the input",
    )

    nullable: bool = Field(
        False,
        description="Whether null values are allowed in this column",
    )

    on_failure: OnFailureBehavior | None = Field(
        None,
        description=(
            "How to handle parsing/check failures:\n"
            "- 'raise': Stop and report errors (default for strict)\n"
            "- 'null': Set failing values to null and continue (requires nullable=True)\n"
            "- None: Inherit from schema profile"
        ),
    )

    @field_validator("dtype")
    @classmethod
    def validate_dtype(cls, v: str) -> str:
        """Validate that dtype is a valid Polars dtype."""
        if not hasattr(pl, v):
            raise ValueError(f"'{v}' is not a valid Polars dtype")
        dtype_obj = getattr(pl, v)
        if not isinstance(dtype_obj, type) or not issubclass(dtype_obj, pl.DataType):
            raise ValueError(f"'{v}' is not a valid Polars DataType")
        return v

    @model_validator(mode="after")
    def validate_on_failure_nullable_consistency(self) -> ColumnSchema:
        """Ensure on_failure='null' requires nullable=True."""
        if self.on_failure == "null" and not self.nullable:
            raise ValueError(
                "on_failure='null' requires nullable=True. "
                "Cannot nullify failures in a non-nullable column."
            )
        return self


class SchemaModel(BaseModel):
    """Top-level schema definition."""

    model_config = ConfigDict(extra="forbid")

    lazy: bool = Field(
        True,
        description="Whether to use Polars lazy execution during validation",
    )

    coerce: bool = Field(
        True,
        description="Whether to coerce columns to the specified dtypes after parsing and validation",
    )

    profile: ValidationProfile = Field(
        "strict",
        description=(
            "Default validation behavior:\n"
            "- 'strict': All failures raise (on_failure='raise' default)\n"
            "- 'clean': Nullify failures for nullable columns\n"
            "- 'audit': Like strict with enhanced reporting"
        ),
    )

    columns: dict[str, ColumnSchema] = Field(
        ..., description="Mapping of column name to its validation schema"
    )
    frame_parsers: list[FrameParser] = Field(
        default_factory=list, description="DataFrame-level parsing functions"
    )

    frame_checks: list[FrameCheck] = Field(
        default_factory=list, description="DataFrame-level checks"
    )

    def __repr__(self) -> str:
        cols = ", ".join(self.columns.keys())
        return f"<SchemaModel lazy={self.lazy}, coerce={self.coerce}, columns=[{cols}]>"

    def resolve_on_failure(self, col_name: str) -> OnFailureBehavior:
        """Resolve effective on_failure for a column.

        Precedence: column explicit > profile default

        Args:
            col_name: Name of the column

        Returns:
            Resolved on_failure behavior
        """
        col_schema = self.columns[col_name]

        if col_schema.on_failure is not None:
            return col_schema.on_failure

        # Profile-based defaults
        if self.profile == "strict":
            return "raise"
        elif self.profile == "clean":
            return "null" if col_schema.nullable else "raise"
        elif self.profile == "audit":
            return "raise"
        else:
            return "raise"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SchemaModel:
        """Load a schema from a dictionary.

        Args:
            data: Dictionary representation of a schema.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ValueError: If validation fails.
        """
        try:
            return cls.model_validate(data)
        except ValidationError as err:
            raise ValueError(f"Invalid schema configuration: {err}") from err

    @classmethod
    def from_python(cls, schema: SchemaModel | Mapping[str, Any]) -> SchemaModel:
        """Accept an existing SchemaModel or a dictionary defining one.

        Args:
            schema: Schema model instance or dictionary.

        Returns:
            SchemaModel: Parsed or passed-through schema.
        """
        if isinstance(schema, cls):
            return schema
        return cls.from_dict(schema)

    @classmethod
    def from_json(cls, content: str) -> SchemaModel:
        """Load a schema from a JSON string.

        Args:
            content: JSON text.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ValueError: If JSON is invalid or schema validation fails.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as err:
            raise ValueError(f"Invalid JSON: {err}") from err
        return cls.from_dict(data)

    @classmethod
    def from_json_file(cls, path: str | Path) -> SchemaModel:
        """Load a schema from a JSON file.

        Args:
            path: Path to JSON schema file.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ValueError: If file cannot be read or schema is invalid.
        """
        try:
            text = Path(path).read_text()
        except OSError as err:
            raise ValueError(f"Cannot read file {path}: {err}") from err
        return cls.from_json(text)

    @classmethod
    def from_yaml(cls, content: str) -> SchemaModel:
        """Load a schema from a YAML string.

        Args:
            content: YAML text.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ImportError: If PyYAML is not installed.
            ValueError: If YAML is invalid or schema validation fails.
        """
        cls._ensure_yaml()
        assert yaml is not None  # for type checkers
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as err:
            raise ValueError(f"Invalid YAML: {err}") from err
        return cls.from_dict(data)

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> SchemaModel:
        """Load a schema from a YAML file.

        Args:
            path: Path to YAML schema file.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ImportError: If PyYAML is not installed.
            ValueError: If file cannot be read or schema is invalid.
        """
        cls._ensure_yaml()
        try:
            text = Path(path).read_text()
        except OSError as err:
            raise ValueError(f"Cannot read file {path}: {err}") from err
        return cls.from_yaml(text)

    @classmethod
    def from_file(cls, path: str | Path) -> SchemaModel:
        """Load a schema from a file, auto-detecting format from extension.

        Args:
            path: Path to schema file (.json, .yaml, or .yml).

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ValueError: If file extension is not recognized or schema is invalid.
        """
        path_obj = Path(path)
        suffix = path_obj.suffix.lower()
        if suffix == ".json":
            return cls.from_json_file(path_obj)
        elif suffix in {".yaml", ".yml"}:
            return cls.from_yaml_file(path_obj)
        else:
            raise ValueError(
                f"Unsupported file extension '{suffix}'. Use .json, .yaml, or .yml"
            )

    @staticmethod
    def _ensure_yaml() -> None:
        """Raise if PyYAML is unavailable."""
        if yaml is None:
            raise ImportError(
                "PyYAML is required for YAML schema loading. "
                "Install with: pip install nyctea[yaml]"
            )
