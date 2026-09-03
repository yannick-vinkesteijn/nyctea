"""Pydantic models describing the validation schema.

This module provides Pydantic models for defining data validation schemas. Schemas
can be defined programmatically or loaded from YAML/JSON files.

The schema defines:
    - Column specifications (dtypes, nullability, parsers, checks)
    - Frame-level operations (parsers and checks)
    - Failure handling (on_failure: raise, null, ignore)
    - Synonym mappings for column names

Example:
    Basic schema definition::

        from nyctea.schema.model import SchemaModel

        schema = SchemaModel.from_dict(
            {"columns": {"age": {"dtype": "Int64", "nullable": False, "checks": [{"name": "positive"}]}}}
        )

    Load from YAML::

        schema = SchemaModel.from_yaml_file("schema.yaml")

Note:
    All schemas are validated at creation time to ensure consistency
    (e.g., `nullable=False` cannot be combined with `on_failure="null"`).
"""

import copy
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import polars as pl
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from nyctea.types import OnFailureBehavior
from nyctea.validators.registry import Registry

if TYPE_CHECKING:
    # The one upward dependency left in the package. `nyctea.engine` reads
    # schemas, so the schema must not import it at module scope.
    # `SchemaModel.validate()` is kept for ergonomics and pays for it with a
    # deferred import, see `tests/test_import_structure.py`.
    from nyctea.engine.results import ValidationResult

# Views derived from the schema's own fields. Built at construction and rebuilt
# after unpickling, so they never need to travel with the object.
_DERIVED_VIEWS: tuple[str, ...] = (
    "canonical_by_accepted_name",
    "accepted_names",
    "resolved_columns",
    "required_columns",
    "non_nullable_columns",
    "columns_with_parsers",
    "columns_with_checks",
    "columns_needing_check_phase",
    "columns_to_coerce",
)


class Parser(BaseModel):
    """Configuration for a column-level parser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., description="Name of the parse function to apply")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the parse function")


class Check(BaseModel):
    """Configuration for a column-level check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., description="Name of the check function to apply")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the check function")


class FrameParser(BaseModel):
    """Configuration for a frame-level parser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., description="Name of the frame-level parser to apply")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the frame parser")


class FrameCheck(BaseModel):
    """Configuration for a frame-level check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., description="Name of the frame-level check to apply")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the frame check")


class ColumnSchema(BaseModel):
    """Schema for a single column."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dtype: str = Field(..., description="The final enforced dtype after validation")
    synonyms: list[str] = Field(default_factory=list, description="Allowed alternative names for this column")

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

    coerce: bool | None = Field(
        None,
        description="Whether to coerce this column to its dtype. None inherits from schema.",
    )

    on_failure: OnFailureBehavior | None = Field(
        None,
        description=(
            "How to handle parsing/coercion/check failures for this column:\n"
            "- 'raise': error, stop\n"
            "- 'null': failure value becomes or remains null (requires nullable=True)\n"
            "- 'ignore': parser/coercion nulls remain, check failures are kept and reported\n"
            "- None: inherit from schema on_failure"
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
            raise TypeError(f"'{v}' is not a valid Polars DataType")
        return v

    @model_validator(mode="after")
    def validate_on_failure_nullable_consistency(self) -> "ColumnSchema":
        """Ensure on_failure='null' requires nullable=True."""
        if self.on_failure == "null" and not self.nullable:
            raise ValueError(
                "on_failure='null' requires nullable=True. Cannot nullify failures in a non-nullable column."
            )
        return self


@dataclass(frozen=True, slots=True)
class ColumnResolution:
    """The outcome of matching a frame's physical column names against a schema.

    Attributes:
        rename: Physical name to canonical name, only where the two differ.
        resolved: Canonical names found in the data, in schema order.
        missing_required: Required canonical names absent from the data, in schema order.
        ambiguous: Canonical name to the several physical names claiming it, for
            columns matched by more than one accepted name.
    """

    rename: Mapping[str, str]
    resolved: tuple[str, ...]
    missing_required: tuple[str, ...]
    ambiguous: Mapping[str, tuple[str, ...]]

    @property
    def is_valid(self) -> bool:
        """Whether the data satisfies the schema's structural requirements."""
        return not self.missing_required and not self.ambiguous


@dataclass(frozen=True, slots=True)
class ResolvedColumn:
    """A column definition with every inherited setting already resolved.

    ``ColumnSchema`` is the authoring shape: it mirrors the YAML a user writes,
    so ``coerce`` and ``on_failure`` are tri-state and ``None`` means "inherit
    from the schema". It also does not carry its own name, since the name is the
    key in ``SchemaModel.columns``.

    Consumers want neither of those things. This is the consumption shape: it
    knows its name and every setting is a concrete value, so a column can answer
    questions about itself without going back through the schema.

    Attributes:
        name: Canonical column name.
        dtype: Declared Polars dtype name.
        synonyms: Alternative accepted names for this column.
        parsers: Parsers applied before checking.
        checks: Checks applied to the parsed column.
        required: Whether the column must be present in the input.
        nullable: Whether null values are allowed.
        coerce: Resolved coercion setting, never None.
        on_failure: Resolved failure behavior, never None.
    """

    name: str
    dtype: str
    synonyms: tuple[str, ...]
    parsers: tuple[Parser, ...]
    checks: tuple[Check, ...]
    required: bool
    nullable: bool
    coerce: bool
    on_failure: OnFailureBehavior

    @property
    def accepted_names(self) -> tuple[str, ...]:
        """Every name this column answers to, canonical first."""
        return (self.name, *self.synonyms)

    @property
    def has_parsers(self) -> bool:
        """Whether this column declares any parser."""
        return bool(self.parsers)

    @property
    def has_checks(self) -> bool:
        """Whether this column declares any check.

        Declared checks only. The not-null constraint is generated rather than
        declared, so it does not count here. See ``needs_check_phase``.
        """
        return bool(self.checks)

    @property
    def needs_check_phase(self) -> bool:
        """Whether the check phase must build a mask for this column.

        True for a non-nullable column even with no declared checks, since the
        not-null mask is generated there.
        """
        return self.has_checks or not self.nullable


class SchemaModel(BaseModel):
    """Top-level schema definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lazy: bool = Field(
        True,
        description="Whether to use Polars lazy execution during validation",
    )

    coerce: bool = Field(
        True,
        description="Whether to coerce columns to the specified dtypes after parsing and validation",
    )

    on_failure: OnFailureBehavior = Field(
        "raise",
        description=(
            "Default failure handling for all columns:\n"
            "- 'raise': error, stop\n"
            "- 'null': failure value becomes or remains null\n"
            "- 'ignore': parser/coercion nulls remain, check failures are kept and reported"
        ),
    )

    streaming_row_threshold: int = Field(
        100_000,
        ge=0,
        description=(
            "Row count at or above which internal reduction-only aggregates (check "
            "and coercion enforcement, summary error counts, report building) use "
            "Polars' streaming engine instead of the in-memory one. Below this, an "
            "eager DataFrame input uses the in-memory engine, since streaming's "
            "fixed pipeline setup cost outweighs the reduction itself on small "
            "data. A LazyFrame input always uses streaming, since its size is "
            "unknown without collecting and choosing lazy signals "
            "larger/out-of-core intent. Those aggregates pass engine= explicitly, "
            "so this threshold overrides any global engine affinity. The 'rows' "
            "and 'cells' error report modes are not aggregates -- they materialise "
            "row indices and values, pass no engine= at all, and so fall to Polars' "
            "own default selection (engine='auto'), which does follow your global "
            "affinity. 0 means always stream."
        ),
    )

    columns: dict[str, ColumnSchema] = Field(..., description="Mapping of column name to its validation schema")
    frame_parsers: list[FrameParser] = Field(default_factory=list, description="DataFrame-level parsing functions")

    frame_checks: list[FrameCheck] = Field(default_factory=list, description="DataFrame-level checks")

    @model_validator(mode="after")
    def validate_name_ownership(self) -> "SchemaModel":
        """Ensure every accepted column name is claimed by exactly one column.

        A schema whose names overlap cannot be resolved unambiguously, so it is
        rejected here rather than at validation time. Reports every conflict at
        once, so a schema with several does not take several rounds to fix.

        Raises:
            ValueError: If any accepted name is claimed more than once.
        """
        claims: dict[str, list[str]] = {}
        for canonical, column in self.columns.items():
            claims.setdefault(canonical, []).append(canonical)
            for synonym in column.synonyms:
                claims.setdefault(synonym, []).append(canonical)

        conflicts: list[str] = []
        for name, claimants in claims.items():
            if len(claimants) == 1:
                continue
            owners = sorted(set(claimants))
            if len(owners) == 1:
                conflicts.append(f"'{name}' is declared more than once by column '{owners[0]}'")
            else:
                listed = ", ".join(f"'{owner}'" for owner in owners)
                conflicts.append(f"'{name}' is claimed by more than one column: {listed}")

        if conflicts:
            raise ValueError("Column names must have exactly one owner. " + "; ".join(sorted(conflicts)))
        return self

    def __repr__(self) -> str:
        """Return string representation of the schema."""
        cols = ", ".join(self.columns.keys())
        return f"<SchemaModel lazy={self.lazy}, coerce={self.coerce}, on_failure={self.on_failure!r}, columns=[{cols}]>"

    # ------------------------------------------------------------------
    # Schema queries
    #
    # Purpose-specific views onto the column definitions, so consumers ask a
    # question once instead of each re-implementing the traversal. Deliberately
    # not one generic field-filter API: named queries keep call sites readable
    # and stay type-safe.
    #
    # The model is frozen, so each view is computed once per schema and reused.
    # Views returning a mapping hand back a read-only proxy, so a caller cannot
    # corrupt the cached value.
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def build_indexes(self) -> "SchemaModel":
        """Compute every derived view now, so a constructed schema is complete.

        Runs after ``validate_name_ownership``, which the indexes rely on: they
        assume every accepted name has exactly one owner.

        The views are ``cached_property``, so touching each one here populates
        it. Doing that at construction rather than on first use means the cost is
        paid once per schema instead of on some later validation run, the frozen
        object never mutates after it exists, and there is no first-call
        latency for a caller to trip over.
        """
        self._build_derived_views()
        return self

    def _build_derived_views(self) -> None:
        """Populate every derived view. Each is a ``cached_property``."""
        for view in _DERIVED_VIEWS:
            getattr(self, view)

    def __getstate__(self) -> dict[str, Any]:
        """Drop the derived views before pickling.

        They hold ``MappingProxyType`` values, which cannot be pickled, and they
        are pure functions of the schema's fields, so rebuilding is both cheap
        and guaranteed to agree.
        """
        state = super().__getstate__()
        state["__dict__"] = {k: v for k, v in state["__dict__"].items() if k not in _DERIVED_VIEWS}
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore the schema and rebuild its derived views."""
        super().__setstate__(state)
        self._build_derived_views()

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> "SchemaModel":
        """Deep-copy the schema's fields and rebuild its derived views.

        Pydantic's default copies ``__dict__`` wholesale, which fails on the
        read-only mappings the derived views hold. Copying only the fields and
        revalidating regenerates them.
        """
        fields = {name: copy.deepcopy(getattr(self, name), memo) for name in type(self).model_fields}
        return type(self).model_validate(fields)

    @cached_property
    def resolved_columns(self) -> Mapping[str, ResolvedColumn]:
        """Every column with its inherited settings already resolved.

        Computed once, when first asked, since the schema is frozen. This is the
        shape consumers should read; ``columns`` is the authoring shape.
        """
        return MappingProxyType(
            {
                name: ResolvedColumn(
                    name=name,
                    dtype=column.dtype,
                    synonyms=tuple(column.synonyms),
                    parsers=tuple(column.parsers),
                    checks=tuple(column.checks),
                    required=column.required,
                    nullable=column.nullable,
                    coerce=self.coerce if column.coerce is None else column.coerce,
                    on_failure=self._resolve_on_failure(name),
                )
                for name, column in self.columns.items()
            }
        )

    def resolve_columns(self, physical_names: Iterable[str]) -> ColumnResolution:
        """Match a frame's physical column names against this schema.

        Pure set work over the schema's cached name index, so nothing about the
        schema is recomputed per call: intersect the physical names with the
        accepted names, reverse-map each match to its canonical column, group to
        find columns claimed by more than one name, and difference against the
        required names to find what is missing.

        Column order does not affect the result.

        Args:
            physical_names: Column names present in the data.

        Returns:
            The resolution, including any ambiguity or missing required columns.
            Inspect ``is_valid`` rather than assuming success.
        """
        index = self.canonical_by_accepted_name
        matched = set(physical_names) & self.accepted_names

        claimed: dict[str, list[str]] = {}
        for physical in sorted(matched):
            claimed.setdefault(index[physical], []).append(physical)

        ambiguous = {canonical: tuple(physicals) for canonical, physicals in claimed.items() if len(physicals) > 1}
        rename = {
            physicals[0]: canonical
            for canonical, physicals in claimed.items()
            if canonical not in ambiguous and physicals[0] != canonical
        }
        # Schema order, so callers and error messages stay deterministic.
        resolved = tuple(name for name in self.columns if name in claimed)
        missing_required = tuple(name for name in self.required_columns if name not in claimed)

        return ColumnResolution(
            rename=MappingProxyType(rename),
            resolved=resolved,
            missing_required=missing_required,
            ambiguous=MappingProxyType(ambiguous),
        )

    def column(self, col_name: str) -> ResolvedColumn:
        """Get one column with its inherited settings resolved.

        Args:
            col_name: Canonical column name.

        Returns:
            The resolved column.

        Raises:
            KeyError: If no column with that canonical name exists.
        """
        return self.resolved_columns[col_name]

    def _resolve_on_failure(self, col_name: str) -> OnFailureBehavior:
        """Resolve on_failure for one column, before ``resolved_columns`` exists."""
        col_schema = self.columns[col_name]
        behavior = col_schema.on_failure if col_schema.on_failure is not None else self.on_failure

        # Guard: can't nullify non-nullable columns. See #25, which tracks making
        # this consistent with the construction-time rejection of the explicit case.
        if behavior == "null" and not col_schema.nullable:
            return "raise"

        return behavior

    @cached_property
    def required_columns(self) -> tuple[str, ...]:
        """Canonical names of columns that must be present in the input."""
        return tuple(name for name, column in self.resolved_columns.items() if column.required)

    @cached_property
    def non_nullable_columns(self) -> tuple[str, ...]:
        """Canonical names of columns that reject null values."""
        return tuple(name for name, column in self.resolved_columns.items() if not column.nullable)

    @cached_property
    def columns_with_parsers(self) -> tuple[str, ...]:
        """Canonical names of columns that declare at least one parser."""
        return tuple(name for name, column in self.resolved_columns.items() if column.has_parsers)

    @cached_property
    def columns_with_checks(self) -> tuple[str, ...]:
        """Canonical names of columns that declare at least one check.

        Declared checks only, matching ``columns_with_parsers``. The not-null
        constraint is generated rather than declared, so it is excluded here. Use
        ``columns_needing_check_phase`` for the wider set the phase acts on.
        """
        return tuple(name for name, column in self.resolved_columns.items() if column.has_checks)

    @cached_property
    def columns_needing_check_phase(self) -> tuple[str, ...]:
        """Canonical names of columns the check phase produces a mask for.

        A non-nullable column needs the phase even with no declared checks, since
        the not-null mask is built there.
        """
        return tuple(name for name, column in self.resolved_columns.items() if column.needs_check_phase)

    @cached_property
    def columns_to_coerce(self) -> tuple[str, ...]:
        """Canonical names of columns whose resolved coerce setting is True."""
        return tuple(name for name, column in self.resolved_columns.items() if column.coerce)

    @cached_property
    def accepted_names(self) -> frozenset[str]:
        """Every exact column name this schema accepts, canonical and synonym alike."""
        return frozenset(self.canonical_by_accepted_name)

    @cached_property
    def canonical_by_accepted_name(self) -> Mapping[str, str]:
        """Reverse index from each accepted name to the canonical column owning it.

        Name ownership is validated at construction, so every accepted name maps
        to exactly one canonical column and this index is unambiguous.

        Returns:
            Mapping of accepted name to canonical name. Canonical names map to
            themselves.
        """
        index: dict[str, str] = {}
        for canonical, column in self.columns.items():
            index[canonical] = canonical
            for synonym in column.synonyms:
                index[synonym] = canonical
        return MappingProxyType(index)

    def resolve_coerce(self, col_name: str) -> bool:
        """Resolve effective coerce setting for a column.

        Resolution order:
        1. Column coerce if set explicitly.
        2. Schema coerce as default.

        Args:
            col_name: Name of the column.

        Returns:
            Whether to coerce this column.
        """
        return self.column(col_name).coerce

    def resolve_on_failure(self, col_name: str) -> OnFailureBehavior:
        """Resolve effective on_failure for a column.

        Resolution order:
        1. Column on_failure if set explicitly.
        2. Schema on_failure as default.
        3. Guard: on_failure=null requires nullable=True. Non-nullable columns
           fall back to raise.

        Args:
            col_name: Name of the column.

        Returns:
            Resolved on_failure behavior.
        """
        return self.column(col_name).on_failure

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SchemaModel":
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
    def from_python(cls, schema: "SchemaModel | Mapping[str, Any]") -> "SchemaModel":
        """Accept an existing SchemaModel or a dictionary defining one.

        Args:
            schema: Schema model instance or dictionary.

        Returns:
            SchemaModel: Parsed or passed-through schema.
        """
        if isinstance(schema, Mapping):
            return cls.from_dict(schema)
        return schema

    @classmethod
    def from_json(cls, content: str) -> "SchemaModel":
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
    def from_json_file(cls, path: str | Path) -> "SchemaModel":
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
    def from_yaml(cls, content: str) -> "SchemaModel":
        """Load a schema from a YAML string.

        Args:
            content: YAML text.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ValueError: If YAML is invalid or schema validation fails.
        """
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as err:
            raise ValueError(f"Invalid YAML: {err}") from err
        return cls.from_dict(data)

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> "SchemaModel":
        """Load a schema from a YAML file.

        Args:
            path: Path to YAML schema file.

        Returns:
            SchemaModel: Parsed schema model.

        Raises:
            ValueError: If file cannot be read or schema is invalid.
        """
        try:
            text = Path(path).read_text()
        except OSError as err:
            raise ValueError(f"Cannot read file {path}: {err}") from err
        return cls.from_yaml(text)

    @classmethod
    def from_file(cls, path: str | Path) -> "SchemaModel":
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
        if suffix in {".yaml", ".yml"}:
            return cls.from_yaml_file(path_obj)
        raise ValueError(f"Unsupported file extension '{suffix}'. Use .json, .yaml, or .yml")

    def validate(  # ty: ignore[invalid-method-override]
        self,
        df: pl.DataFrame | pl.LazyFrame,
        registry: Registry,
        **kwargs: Any,
    ) -> "ValidationResult":
        """Validate a DataFrame against this schema.

        This is the primary API for validation using the new validator-based
        pipeline architecture.

        Args:
            df: DataFrame to validate.
            registry: Validator registry with parsers and checks.
            **kwargs: Additional validation options passed to SchemaValidator.

        Returns:
            ValidationResult with validated data, errors, and report.

        Raises:
            ValidationError: If validation fails in strict mode.
            PipelineError: If pipeline execution fails.

        Example:
            >>> from nyctea.validators.registry import Registry
            >>> schema = SchemaModel.from_yaml("schema.yaml")
            >>> registry = Registry()
            >>> # ... register validators ...
            >>> result = schema.validate(df, registry)
            >>> print(result.report.summary())
        """
        from nyctea.engine.validator import SchemaValidator

        validator = SchemaValidator(self, registry)
        return validator.validate(df, **kwargs)
