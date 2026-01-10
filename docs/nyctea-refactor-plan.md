# Nyctea OOP Architecture Refactoring Plan

______________________________________________________________________

## 🎉 Sprint 1 Complete! (January 2026)

**Status:** ✅ **Minimal Working Implementation Delivered**

### What We Built

In an agile sprint, we delivered the **core foundation** of the OOP architecture:

**✅ Phases 1-4 (Core Foundation)**

- [x] Plugin system with strict enforcement (purity, shape, signatures)
- [x] Type-safe generic registries with collision detection
- [x] Customizable validation pipeline with dependency enforcement
- [x] Observability hooks (logging, metrics collection)
- [x] Schema-centric API: `schema.validate(df, registry)`
- [x] Built-in plugins (5 parsers, 4 checks)
- [x] Functional decorator API
- [x] 3 core pipeline phases implemented
- [x] Comprehensive documentation

**📊 Metrics:**

- **18 new files** created (~2,150 LOC)
- **Working test:** `test_minimal.py` validates successfully
- **Code quality:** Ruff linting passed
- **Documentation:** 600+ lines across 4 guides

**📁 Key Files:**

- `src/nyctea/plugins/` - Complete plugin system
- `src/nyctea/engine/pipeline.py` - Pipeline with dependency validation
- `src/nyctea/schema/validator.py` - SchemaValidator class
- See [SPRINT_1_COMPLETE.md](../SPRINT_1_COMPLETE.md) for full details

### What's Next (Sprint 2+)

**Priority: Complete Pipeline for Titanic Example**

- [ ] FrameParsingPhase & FrameCheckPhase (needed for Titanic)
- [ ] Remaining 8 phases (coercion, error reporting, nullification, etc.)
- [ ] Comprehensive error reporting (rows/cells mode)
- [ ] Full test suite
- [ ] Performance benchmarks

**Updated Timeline:**

- Sprint 1 (DONE): Core foundation - 1 day
- Sprint 2 (NEXT): Frame support + Titanic validation - 2-3 days
- Sprint 3: Complete all 11 phases - 2-3 days
- Sprint 4: Testing + performance - 2 days
- Sprint 5: Reader plugins + streaming - 2 days
- Sprint 6: Documentation + release - 1 day

**See [REFACTOR_SUMMARY.md](../REFACTOR_SUMMARY.md) for implementation details.**

______________________________________________________________________

## Original Plan Overview

Transform Nyctea from a functional/procedural architecture into a production-ready OOP system with:

- **Heavy inheritance-based design** for plugins ✅ DONE
- **Fully customizable validation pipeline** (add/remove/reorder phases) ✅ DONE
- **Schema-centric API**: `schema.validate(df)` ✅ DONE
- **Explicit plugin registration** (decorator-based) ✅ DONE
- **Strict dimension and I/O validation** for parsers/checks ✅ DONE

## Critical Context for Future Implementation

### What Nyctea Is

Nyctea is a **Polars-based data validation library** (like Pandera, but for Polars instead of Pandas). It validates tabular data against declarative YAML schemas with custom parsers and checks.

**Current Working Features** (v0.1):

- Read CSV/Parquet with schema awareness
- Validate data against Pydantic-based schemas
- Custom parsers (column transformations) and checks (validations)
- Function registry for extensibility
- Three validation profiles: strict, clean, audit
- Comprehensive error reporting

**What Works Well**:

- Schema definition via YAML/JSON/Python
- Synonym support for column names
- Lazy evaluation throughout
- Integration with Polars expressions

### Why This Refactor?

The user wants:

1. **OOP design** - Heavy use of inheritance, not functional programming
1. **Plugin architecture** - Base classes that can be extended
1. **Pipeline customization** - Users should be able to add/remove/reorder validation phases
1. **Production-ready** - Proper error handling, logging, observability
1. **Pythonic & efficient** - Follow Polars best practices, PEP 8, strict Ruff linting

### User's Design Philosophy

- **Loves OOP** - Prefers class-based design with clear inheritance hierarchies
- **Plugin-first thinking** - Everything should be a plugin with a base class
- **Clean architecture** - Modular, separated concerns, SOLID principles
- **Type safety** - Generics + runtime validation
- **Efficiency** - Lazy evaluation, minimal `.collect()` calls, batch operations
- **Strict validation** - Enforce column purity, shape preservation at runtime

### Non-Negotiables

1. **Polars must stay lazy** - Work with LazyFrame by default, only collect at the end
1. **Column purity** - Column parsers/checks can only reference the input column
1. **Schema-centric API** - `schema.validate(df, registry)` is the primary interface
1. **No backward compatibility needed** - This is v0.1, clean slate for v0.2
1. **Ruff linting** - Must pass strict PEP 8 compliance
1. **Google-style docstrings** - For all public APIs (auto-generated docs with Zensical)

### Key Existing Implementation Details

**Current Files to Study** (before refactoring):

- `src/nyctea/engine/validate.py` - 240-line monolithic validation function with 12 phases
- `src/nyctea/functions/registry.py` - Dictionary-based function registry with wrappers
- `src/nyctea/schema/model.py` - Pydantic schema models (SchemaModel, ColumnSchema)
- `src/nyctea/ingest/readers.py` - CSV/Parquet readers (recently optimized with `infer_schema=False`)

**Current Validation Pipeline** (12 phases to preserve):

1. Column resolution (synonym mapping)
1. Count original nulls
1. Frame parsers
1. Column parsers
1. Type coercion (if `schema.coerce=True`)
1. Frame checks
1. Column checks (with auto-injected `non_null` for `nullable=False`)
1. Error report building
1. Lenient nullification (if `coerce_strategy="null_on_failure"`)
1. Final nullable check
1. Report generation
1. Return ValidationResult

**Important Schema Features**:

- **Synonyms**: Map physical column names (e.g., "PassengerId") to canonical names (e.g., "passenger_id")
- **Validation profiles**: "strict" (raise), "clean" (nullify), "audit" (raise + enhanced reporting)
- **Coercion modes**: Schema has `coerce: bool` flag, runtime has `coerce_strategy: "strict" | "null_on_failure"`
- **Auto-injection**: Non-null check auto-injected when `nullable: false` (avoid duplicates)

**Working Examples** (test against these):

- `examples/titanic_example/` - Contains working schema.yaml and titanic_nb.py
- Example uses parsers (`strip`, `to_int`, `to_float`) and checks (`unique_passenger_id`)
- Schema has `coerce: false` because parsers already handle type conversion

### Implementation Strategy Decisions

**Why Plugin Base Classes?**

- Current registry uses dictionaries with string keys → no type safety
- Wrappers enforce purity/shape at runtime → should be part of base class `__call__`
- No clear inheritance hierarchy → hard to extend with new plugin types

**Why Pipeline Phases?**

- Current 240-line `validate()` function is monolithic → hard to test, extend
- Fixed phase order → users can't customize (requested feature)
- Each phase has clear responsibility → extract to class with `execute(context)`

**Why Schema-Centric API?**

- Current: `validate(lf, schema, registry)` - function-based
- Target: `schema.validate(df, registry)` - schema owns validation
- More intuitive: schema knows what valid data looks like, so it should validate

**Why PipelineContext?**

- Current: Local variables in `validate()` function
- Target: Shared context object passed through phases
- Benefit: Phases can accumulate state, easier to debug, cleaner code

### Common Pitfalls to Avoid

1. **Don't break Polars laziness** - Never add unnecessary `.collect()` calls
1. **Don't lose column purity** - Must enforce at runtime via `__call__` wrapper
1. **Don't change validation logic** - Only refactor structure, preserve behavior
1. **Don't create circular imports** - Use forward references with `TYPE_CHECKING`
1. **Don't skip docstrings** - Every public class/method needs Google-style docs
1. **Don't forget `__all__`** - Explicit exports for every module
1. **Don't mix concerns** - One responsibility per class (SRP)
1. **Don't use `Any`** - Use proper type hints with generics

### Testing Requirements

**Must Pass**:

- All existing titanic example tests
- Ruff linting with no errors
- Type checking with pyright/mypy
- Performance at least as good as v0.1

**New Tests Needed**:

- Unit tests for each plugin base class
- Unit tests for each phase implementation
- Integration tests for full pipeline
- Tests for pipeline customization (add/remove/reorder)
- Tests for plugin registration (collision, type validation)

### Pipeline Customization Constraints

**CRITICAL**: While users can customize the pipeline, **schema guarantees must always be enforced**.

**Schema-Driven Phases** (MUST always run):

1. **Column resolution** - If schema has synonyms, they must be resolved
1. **Nullable enforcement** - If `nullable: false`, non-null checks are mandatory
1. **Required columns** - If `required: true`, column must exist
1. **Type coercion** - If `schema.coerce: true`, coercion phase must run
1. **User-defined checks** - All checks in schema must execute

**User Customization Options**:

- ✅ **Add custom phases** - Insert additional validation/transformation logic
- ✅ **Reorder flexible phases** - Change order of parsers, checks (within constraints)
- ✅ **Add hooks/observers** - Inject logging, metrics, auditing
- ❌ **Cannot skip schema-required phases** - If schema defines it, it must run
- ❌ **Cannot violate dependencies** - Parsing before coercion, checks after coercion

**Two-Tier Pipeline Design**:

```python
# Tier 1: Schema-required phases (automatically added based on schema)
required_phases = pipeline.build_required_phases(schema)

# Tier 2: User-customizable phases (can add/remove/reorder these)
custom_phases = []

# Final pipeline: Required + Custom, with dependency validation
final_pipeline = pipeline.merge(required_phases, custom_phases)
```

**Example Constraint Enforcement**:

```python
# User tries to remove nullable check
validator = schema.create_validator(registry)
validator.pipeline.remove_phase("final_nullable_check")

# ❌ Should raise error:
# "Cannot remove 'final_nullable_check': required by schema (3 columns have nullable=false)"

# ✅ But this is OK:
validator.pipeline.remove_phase("coercion")  # Only if schema.coerce=false

# ✅ This is also OK:
validator.pipeline.add_phase(AuditPhase(), after="column_checks")
```

**Phase Dependencies**:

```
Column Resolution (required if synonyms exist)
  ↓
Null Counting (always required)
  ↓
Frame Parsers (required if schema has frame_parsers)
  ↓
Column Parsers (required if schema has parsers)
  ↓
Coercion (required if schema.coerce=true)
  ↓
Frame Checks (required if schema has frame_checks)
  ↓
Column Checks (required if schema has checks OR nullable=false)
  ↓
Error Reporting (always required)
  ↓
Nullification (required if coerce_strategy="null_on_failure")
  ↓
Final Nullable Check (required if any column has nullable=false)
  ↓
Report Generation (always required)
```

**Implementation Strategy**:

```python
class ValidationPipeline:
    def __init__(self, schema: SchemaModel):
        self._schema = schema
        self._required_phases = self._build_required_phases()
        self._custom_phases = []
        self._locked = False  # Lock after validation starts

    def _build_required_phases(self) -> list[PipelinePhase]:
        """Build phases that schema requires."""
        phases = []

        # Always required
        phases.append(ColumnResolutionPhase())
        phases.append(NullCountingPhase())

        # Conditionally required based on schema
        if self._schema.frame_parsers:
            phases.append(FrameParsingPhase())

        if any(col.parsers for col in self._schema.columns.values()):
            phases.append(ColumnParsingPhase())

        if self._schema.coerce:
            phases.append(CoercionPhase())

        # ... etc

        return phases

    def add_phase(
        self,
        phase: PipelinePhase,
        *,
        after: str | None = None
    ) -> None:
        """Add custom phase (must not conflict with required phases)."""
        if self._locked:
            raise ValueError("Cannot modify pipeline after validation started")

        # Validate phase doesn't conflict with required phases
        self._validate_phase_compatibility(phase)

        self._custom_phases.append((phase, after))

    def remove_phase(self, name: str) -> None:
        """Remove phase (only if not required by schema)."""
        if self._locked:
            raise ValueError("Cannot modify pipeline after validation started")

        # Check if phase is required
        for required_phase in self._required_phases:
            if required_phase.name == name:
                raise ValueError(
                    f"Cannot remove '{name}': required by schema. "
                    f"Reason: {self._get_requirement_reason(name)}"
                )

        # Remove from custom phases
        self._custom_phases = [
            (p, a) for p, a in self._custom_phases
            if p.name != name
        ]

    def _get_requirement_reason(self, phase_name: str) -> str:
        """Explain why phase is required."""
        if phase_name == "final_nullable_check":
            non_nullable_cols = [
                name for name, col in self._schema.columns.items()
                if not col.nullable
            ]
            return f"{len(non_nullable_cols)} columns have nullable=false"

        if phase_name == "coercion":
            return f"schema.coerce is true"

        # ... etc

    def build(self) -> list[PipelinePhase]:
        """Build final ordered phase list."""
        # Merge required and custom phases
        # Validate dependencies
        # Return final ordered list
        pass
```

### Validation Result Tracking

**ValidationResult must track which phases ran**:

```python
@dataclass
class ValidationResult:
    """Results from validation pipeline execution."""
    data: pl.DataFrame | pl.LazyFrame
    errors: pl.DataFrame | None
    report: ValidationReport

    # NEW: Track what actually happened
    phases_executed: list[str]  # Names of phases that ran
    phases_skipped: list[str]   # Phases skipped (with reasons)
    schema_violations: list[str]  # Schema requirements that weren't met

    def was_fully_validated(self) -> bool:
        """Check if all schema requirements were met."""
        return len(self.schema_violations) == 0

    def get_validation_summary(self) -> dict[str, Any]:
        """Get summary of what validation did."""
        return {
            "phases_run": len(self.phases_executed),
            "phases_skipped": len(self.phases_skipped),
            "schema_compliant": self.was_fully_validated(),
            "violations": self.schema_violations,
        }
```

**Example Output**:

```python
result = schema.validate(df, registry)

print(result.get_validation_summary())
# {
#     "phases_run": 11,
#     "phases_skipped": 1,  # Coercion skipped (schema.coerce=false)
#     "schema_compliant": True,
#     "violations": []
# }

# If user incorrectly removed required phase:
validator = schema.create_validator(registry)
validator.pipeline.remove_phase("column_checks")  # User mistake

# ❌ Raises: "Cannot remove 'column_checks': required by schema (5 checks defined)"
```

### Valid Phase Configurations and Ordering Constraints

**CRITICAL PRINCIPLE**: Phases are defined by the schema. Users adjust the schema to control what validation happens. The pipeline automatically builds the required phases based on schema definition.

#### Schema Controls Pipeline Structure

The schema is the single source of truth for validation behavior:

```yaml
# schema.yaml - This defines what phases run
columns:
  age:
    dtype: Int64
    nullable: false  # ✅ Auto-adds: NullableCheckPhase
    parsers:         # ✅ Auto-adds: ColumnParsingPhase
      - name: to_int
    checks:          # ✅ Auto-adds: ColumnCheckPhase
      - name: positive

coerce: true         # ✅ Auto-adds: CoercionPhase
```

**Pipeline automatically builds required phases from schema**:

- If `coerce: true` → CoercionPhase is included
- If any column has `nullable: false` → FinalNullableCheckPhase is included
- If any column defines `parsers` → ColumnParsingPhase is included
- If any column defines `checks` → ColumnCheckPhase is included
- If schema defines `frame_parsers` → FrameParsingPhase is included
- If schema defines `frame_checks` → FrameCheckPhase is included

#### Logically Valid Phase Orderings

These orderings are **correct and will be enforced** by the pipeline:

1. **Parse → Coerce → Check** (Standard Flow):

    ```
    ColumnParsing → Coercion → ColumnChecks
    ```

    - ✅ **Why valid**: Parse cleans data (e.g., strip whitespace), coerce converts types, checks validate final values
    - Example: `strip("  42  ")` → coerce to Int64 → check `> 0`

1. **Parse → Check (No Coercion)** (When `coerce: false`):

    ```
    ColumnParsing → ColumnChecks
    ```

    - ✅ **Why valid**: Parsers handle type conversion themselves, checks validate results
    - Example (Titanic): `to_int("42")` returns Int64 → check `unique_passenger_id`

1. **Frame Operations Before Column Operations**:

    ```
    FrameParsing → FrameChecks → ColumnParsing → ColumnChecks
    ```

    - ✅ **Why valid**: Frame-level transformations (e.g., add computed columns) before column-level validation
    - Example: Add `age_group` column → validate it exists → parse `age` → check `age > 0`

1. **Null Counting Before Everything**:

    ```
    NullCounting → [all other phases]
    ```

    - ✅ **Why valid**: Need baseline null counts before any transformations for reporting

1. **Error Reporting After Checks**:

    ```
    [all checks] → ErrorReporting → Nullification → FinalNullableCheck
    ```

    - ✅ **Why valid**: Collect errors, optionally nullify failures, then validate final nulls

#### Logically Invalid Orderings (Prevented by Pipeline)

These orderings are **incorrect and must be prevented**:

1. **❌ Check Before Parse**:

    ```
    ColumnChecks → ColumnParsing  # INVALID!
    ```

    - **Why invalid**: Checking untransformed/dirty data
    - Example: Check email format on `"  user@example.com  "` (fails due to whitespace) → then trim
    - **Pipeline error**: `"ColumnCheckPhase requires ColumnParsingPhase to run first"`

1. **❌ Check Before Coerce**:

    ```
    ColumnChecks → Coercion  # INVALID!
    ```

    - **Why invalid**: Validating wrong types
    - Example: Check `age > 18` on string `"25"` (fails) → then coerce to Int64
    - **Pipeline error**: `"ColumnCheckPhase requires CoercionPhase to run first (schema.coerce=true)"`

1. **❌ Coerce Before Parse**:

    ```
    Coercion → ColumnParsing  # INVALID!
    ```

    - **Why invalid**: Type casting dirty data
    - Example: Coerce `"  42  "` to Int64 (fails due to whitespace) → then trim
    - **Pipeline error**: `"CoercionPhase requires ColumnParsingPhase to run first"`

1. **❌ Nullable Check Before Coercion**:

    ```
    FinalNullableCheck → Coercion  # INVALID!
    ```

    - **Why invalid**: Checking nulls on wrong types (coercion may produce nulls on failure)
    - **Pipeline error**: `"FinalNullableCheckPhase must run after CoercionPhase"`

1. **❌ Error Reporting Before Checks Complete**:

    ```
    ColumnChecks → ErrorReporting → FrameChecks  # INVALID!
    ```

    - **Why invalid**: Incomplete error collection
    - **Pipeline error**: `"ErrorReportingPhase must run after all check phases"`

#### Phase Dependency Rules

Each phase declares its dependencies. The pipeline validates dependencies when building the phase list.

**Hard Dependencies** (MUST be satisfied):

| Phase                | Must Run After                                 | Reason                                         |
| -------------------- | ---------------------------------------------- | ---------------------------------------------- |
| `ColumnParsing`      | `ColumnResolution`, `NullCounting`             | Need resolved column names and null baseline   |
| `Coercion`           | `ColumnParsing` (if parsers exist)             | Parse before type cast                         |
| `ColumnChecks`       | `ColumnParsing`, `Coercion` (if `coerce=true`) | Validate transformed, typed data               |
| `FrameChecks`        | `FrameParsing` (if frame parsers exist)        | Frame transformations before frame validation  |
| `ErrorReporting`     | All check phases                               | Need complete error list                       |
| `Nullification`      | `ErrorReporting`                               | Need error report to know what to nullify      |
| `FinalNullableCheck` | `Nullification`, `Coercion`                    | Validate final state after all transformations |
| `ReportGeneration`   | `FinalNullableCheck`                           | Generate report at end                         |

**Soft Dependencies** (recommended but not enforced):

| Phase          | Recommended After  | Reason                                   |
| -------------- | ------------------ | ---------------------------------------- |
| `FrameParsing` | `ColumnResolution` | Resolved names for frame operations      |
| `FrameChecks`  | `ColumnParsing`    | Column values available for frame checks |

#### Schema-Based Mandatory Orderings

Based on schema configuration, certain orderings are **automatically enforced**:

1. **If `coerce: true`**:

    ```
    ColumnParsing (if exists) → Coercion → ColumnChecks
    ```

    - Cannot reorder coercion before parsing
    - Cannot skip coercion phase

1. **If any column has `nullable: false`**:

    ```
    [all transformations] → FinalNullableCheck
    ```

    - FinalNullableCheck must be last validation phase
    - Cannot skip this phase

1. **If both parsers and checks exist**:

    ```
    ColumnParsing → ColumnChecks
    ```

    - Parsers always before checks
    - Cannot interleave them

1. **If `coerce_strategy: "null_on_failure"`** (runtime option):

    ```
    ErrorReporting → Nullification → FinalNullableCheck
    ```

    - Nullification must happen after error reporting
    - Final nullable check must validate nullified data

#### Custom Phase Insertion Rules

Users can add custom phases, but must respect dependencies:

**✅ ALLOWED Custom Insertions**:

```python
# Add audit phase after checks
validator.pipeline.add_phase(
    AuditPhase(),
    after="column_checks"
)
# Valid: No dependency violations

# Add enrichment before parsing
validator.pipeline.add_phase(
    EnrichmentPhase(),
    after="column_resolution"
)
# Valid: Can add data before transformations

# Add logging observer at any point
validator.pipeline.add_phase(
    LoggingPhase(),
    after="null_counting"
)
# Valid: Observers have no dependencies
```

**❌ REJECTED Custom Insertions**:

```python
# Try to add phase that breaks dependencies
validator.pipeline.add_phase(
    CustomCheckPhase(),
    after="column_parsing",
    before="coercion"  # If coercion is required
)
# ❌ Error: "CustomCheckPhase would run before CoercionPhase, but ColumnCheckPhase requires coercion to run first"

# Try to insert between hard dependencies
validator.pipeline.add_phase(
    CustomPhase(),
    after="error_reporting",
    before="nullification"  # If nullification is required
)
# ❌ Error: "Cannot insert phase between ErrorReportingPhase and NullificationPhase (hard dependency)"
```

#### Validation Strategy for Custom Phases

When a user adds a custom phase, the pipeline:

1. **Builds dependency graph** from all required phases
1. **Validates insertion point** doesn't break dependencies
1. **Topological sort** to ensure valid ordering
1. **Raises descriptive error** if insertion violates constraints

**Example Implementation**:

```python
class ValidationPipeline:
    def add_phase(
        self,
        phase: PipelinePhase,
        *,
        after: str | None = None,
        before: str | None = None
    ) -> None:
        """Add custom phase with dependency validation."""

        # Build dependency graph
        dep_graph = self._build_dependency_graph()

        # Find insertion point
        insert_after = self._find_phase(after) if after else None
        insert_before = self._find_phase(before) if before else None

        # Validate insertion doesn't break dependencies
        if insert_after and insert_before:
            # Check if any phase between insert points depends on phase after insert_before
            phases_between = self._get_phases_between(insert_after, insert_before)
            for p in phases_between:
                if insert_before.name in p.dependencies:
                    raise PipelineError(
                        f"Cannot insert {phase.name} between {insert_after.name} "
                        f"and {insert_before.name}: {p.name} depends on {insert_before.name}"
                    )

        # Add to custom phases
        self._custom_phases.append((phase, after, before))
```

#### Schema Adjustment Examples

**Example 1: Remove Coercion**

Instead of removing the phase, adjust the schema:

```yaml
# ❌ OLD: Try to remove phase
# validator.pipeline.remove_phase("coercion")  # Error if coerce=true

# ✅ NEW: Adjust schema
coerce: false  # Coercion phase not added
columns:
  age:
    parsers:
      - name: to_int  # Parser handles type conversion
```

**Example 2: Change Validation Strictness**

```yaml
# ❌ OLD: Try to skip nullable check
# validator.pipeline.remove_phase("final_nullable_check")  # Error if any nullable=false

# ✅ NEW: Adjust schema
columns:
  name:
    nullable: true   # Changed from false
  email:
    nullable: true   # Changed from false
```

**Example 3: Reorder Checks**

You can't reorder phases, but you can order checks within a column:

```yaml
columns:
  age:
    checks:
      - name: not_null    # Runs first
      - name: positive    # Then this
      - name: reasonable  # Then this
```

All checks still run in the ColumnCheckPhase, but within that phase they execute in schema order.

#### Configuration Validation at Pipeline Build Time

When the pipeline builds from schema:

```python
class ValidationPipeline:
    @classmethod
    def from_schema(cls, schema: SchemaModel) -> "ValidationPipeline":
        """Build pipeline from schema definition."""

        phases = []

        # Always required (in order)
        phases.append(ColumnResolutionPhase())
        phases.append(NullCountingPhase())

        # Conditionally required based on schema
        has_frame_parsers = bool(schema.frame_parsers)
        has_column_parsers = any(col.parsers for col in schema.columns.values())
        has_coercion = schema.coerce
        has_frame_checks = bool(schema.frame_checks)
        has_column_checks = any(
            col.checks or not col.nullable
            for col in schema.columns.values()
        )

        # Frame operations first
        if has_frame_parsers:
            phases.append(FrameParsingPhase())

        if has_frame_checks:
            phases.append(FrameCheckPhase())

        # Column operations
        if has_column_parsers:
            phases.append(ColumnParsingPhase())

        if has_coercion:
            phases.append(CoercionPhase())

        if has_column_checks:
            phases.append(ColumnCheckPhase())

        # Error handling (always required)
        phases.append(ErrorReportingPhase())

        # Conditionally required based on runtime strategy
        # (added dynamically during validation)

        # Final validation (always required)
        phases.append(FinalNullableCheckPhase())
        phases.append(ReportGenerationPhase())

        # Validate dependencies
        cls._validate_phase_ordering(phases)

        return cls(phases, schema)

    @staticmethod
    def _validate_phase_ordering(phases: list[PipelinePhase]) -> None:
        """Ensure phase ordering satisfies all dependencies."""
        phase_names = [p.name for p in phases]

        for i, phase in enumerate(phases):
            for dep in phase.dependencies:
                if dep not in phase_names[:i]:
                    raise PipelineError(
                        f"Phase '{phase.name}' at position {i} depends on '{dep}', "
                        f"but '{dep}' has not run yet. "
                        f"Current ordering: {phase_names}"
                    )
```

#### Summary: What Users Can and Cannot Do

**✅ Users CAN**:

- Define schema with `coerce`, `nullable`, `parsers`, `checks`
- Add custom phases at valid insertion points
- Add observers/hooks for monitoring
- Configure validation profiles (`strict`, `clean`, `audit`)
- Set runtime strategies (`coerce_strategy`)

**❌ Users CANNOT**:

- Remove schema-required phases
- Reorder phases in a way that violates dependencies
- Skip validation steps defined in schema
- Insert phases that break hard dependencies
- Change phase execution order arbitrarily

**The Golden Rule**:

> If you want different validation behavior, modify the schema. The pipeline automatically builds the correct phase sequence from your schema definition.

### Questions to Clarify Before Starting

If unsure about any of these, ask the user:

1. **Phase dependency strictness?** - Should we prevent ALL invalid orderings, or just warn?
1. **Schema violation behavior?** - Should pipeline refuse to run if schema requirements can't be met, or run with warnings?
1. **Custom phase validation?** - Should custom phases declare their dependencies/requirements?
1. **Pipeline presets?** - Should we provide 2-3 preset pipelines (minimal, standard, comprehensive)?
1. **Hook system?** - Should we add before/after hooks for each phase for observability?

### What Success Looks Like

**After Phase 1** (Plugin Foundation):

```python
from nyctea.plugins.column import ColumnParser
from nyctea.plugins.base import PluginMetadata

class TrimParser(ColumnParser):
    def __init__(self):
        super().__init__(PluginMetadata(name="trim"))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        return column.str.strip_chars()

    def validate_args(self, **kwargs) -> None:
        pass  # No args to validate

parser = TrimParser()
result = parser(pl.col("name"))  # Enforces purity
```

**After Phase 4** (Schema Integration):

```python
from nyctea.schema.model import SchemaModel
from nyctea.plugins.registry import MasterRegistry

schema = SchemaModel.from_yaml("schema.yaml")
registry = MasterRegistry()
# ... register plugins ...

result = schema.validate(df, registry)
print(f"Valid: {len(result.data)} rows")
```

**After Phase 3** (Custom Pipeline):

```python
validator = schema.create_validator(registry)

# Remove coercion
validator.pipeline.remove_phase("coercion")

# Add custom phase
validator.pipeline.add_phase(
    MyAuditPhase(),
    after="column_checks"
)

result = validator.validate(df)
```

## Architecture Summary

### Current State (v0.1)

- **Monolithic**: 240-line `validate()` function with 12 fixed phases
- **Dictionary-based**: Function registry using plain dicts with string keys
- **Functional**: No OOP abstractions, procedural pipeline
- **Limited extensibility**: Can only add functions, not customize pipeline

### Target State (v0.2)

- **OOP Plugin System**: Base classes for all extensions
- **Customizable Pipeline**: Add/remove/reorder validation phases
- **Type-Safe Registry**: Generic plugin registry with metadata
- **Production-Ready**: Comprehensive error handling, logging, configuration

## Code Style & Engineering Principles

### Python Style Guidelines

**PEP 8 Compliance** (Enforced by Ruff):

- Line length: 100 characters maximum
- Use 4 spaces for indentation (never tabs)
- Two blank lines between top-level classes/functions
- One blank line between methods
- Import order: stdlib → third-party → local (use `isort` profile)
- Type hints required for all public APIs
- Docstrings required for all public modules, classes, functions

**Naming Conventions**:

- Classes: `PascalCase` (e.g., `ColumnParser`, `ValidationPipeline`)
- Functions/methods: `snake_case` (e.g., `validate_args`, `execute_phase`)
- Private methods: `_leading_underscore` (e.g., `_validate_input`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_ERROR_ROWS`)
- Type variables: `T`, `TInput`, `TOutput` (generic single letter or prefixed)

**Docstring Format** (Google Style):

```python
def validate(self, df: pl.DataFrame, **kwargs) -> ValidationResult:
    """Execute validation pipeline on a DataFrame.

    This method runs all configured pipeline phases in sequence, collecting
    validation errors and generating a comprehensive report.

    Args:
        df: Input DataFrame to validate.
        **kwargs: Additional validation options.
            coerce_strategy: "strict" or "null_on_failure".
            lazy: Override schema lazy setting.

    Returns:
        ValidationResult containing validated data, errors, and report.

    Raises:
        ValidationError: If validation fails in strict mode.
        PipelineError: If pipeline execution encounters an error.

    Example:
        >>> schema = SchemaModel.from_yaml("schema.yaml")
        >>> result = schema.validate(df, registry)
        >>> print(f"Valid rows: {len(result.data)}")
    """
```

### Polars-Specific Best Practices

**Lazy Evaluation First**:

```python
# ✅ GOOD: Work with LazyFrame by default
def validate(self, df: pl.DataFrame | pl.LazyFrame) -> ValidationResult:
    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    # ... work with lf ...
    return result  # Collect only at the end

# ❌ BAD: Unnecessary eager evaluation
def validate(self, df: pl.DataFrame) -> ValidationResult:
    df = df.collect()  # Forces computation too early
```

**Expression Building**:

```python
# ✅ GOOD: Chain expressions fluently
expr = (
    pl.col("age")
    .cast(pl.Int64)
    .fill_null(strategy="zero")
    .clip(lower=0, upper=120)
)

# ✅ GOOD: Use .pipe() for custom transformations
expr = pl.col("email").pipe(validate_email)

# ❌ BAD: Multiple passes over data
df = df.with_columns(pl.col("age").cast(pl.Int64))
df = df.with_columns(pl.col("age").fill_null(0))  # Separate pass
```

**Column Purity**:

```python
# ✅ GOOD: Single column in, single column out
def trim_whitespace(col: pl.Expr) -> pl.Expr:
    """Pure transformation - only references input column."""
    return col.str.strip_chars()

# ❌ BAD: References multiple columns (impure)
def compute_ratio(col: pl.Expr) -> pl.Expr:
    return col / pl.col("total")  # References 'total' column
```

**Minimize .collect() Calls**:

```python
# ✅ GOOD: Single collect at end
lf = (
    pl.scan_csv("data.csv")
    .filter(pl.col("age") > 18)
    .select(["name", "age", "email"])
)
result = lf.collect()  # Only materialize once

# ❌ BAD: Multiple collects
df = pl.scan_csv("data.csv").collect()  # Unnecessary
df = df.filter(pl.col("age") > 18).collect()  # Another unnecessary
```

### Software Engineering Principles

**1. Single Responsibility Principle (SRP)**:

```python
# ✅ GOOD: Each class has one responsibility
class ColumnParser(ColumnPlugin):
    """Responsible only for column transformation."""

class ColumnCheck(ColumnPlugin):
    """Responsible only for column validation."""

# ❌ BAD: Mixed responsibilities
class ColumnProcessor:
    """Handles both transformation AND validation."""
```

**2. Open/Closed Principle (OCP)**:

```python
# ✅ GOOD: Open for extension via inheritance
class BasePlugin(ABC):
    @abstractmethod
    def execute(self, input_data, **kwargs):
        pass

class EmailValidator(ColumnCheck):  # Extends without modifying base
    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        return column.str.contains(r'^.+@.+\..+$')

# ❌ BAD: Modifying base class for each new feature
```

**3. Liskov Substitution Principle (LSP)**:

```python
# ✅ GOOD: Subtypes maintain base class contract
class ColumnParser(ColumnPlugin):
    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        # Always returns pl.Expr as expected
        return column.str.to_uppercase()

# ❌ BAD: Violates contract
class BadParser(ColumnPlugin):
    def execute(self, column: pl.Expr, **kwargs) -> str:
        # Returns wrong type!
        return "invalid"
```

**4. Interface Segregation Principle (ISP)**:

```python
# ✅ GOOD: Minimal, focused interfaces
class PipelinePhase(ABC):
    @abstractmethod
    def execute(self, context: PipelineContext) -> PipelineContext:
        pass

    def can_skip(self, context: PipelineContext) -> bool:
        return False  # Optional override

# ❌ BAD: Fat interface with methods not all implementations need
class PipelinePhase(ABC):
    @abstractmethod
    def execute(self, context): pass
    @abstractmethod
    def rollback(self, context): pass  # Not all phases need this
    @abstractmethod
    def validate_preconditions(self, context): pass
```

**5. Dependency Inversion Principle (DIP)**:

```python
# ✅ GOOD: Depend on abstractions
class ValidationPipeline:
    def __init__(self, phases: list[PipelinePhase]):  # Abstract type
        self.phases = phases

# ❌ BAD: Depend on concrete types
class ValidationPipeline:
    def __init__(self, phases: list[CoercionPhase]):  # Too specific
        self.phases = phases
```

### Plugin Architecture Principles

**1. Modularity**:

- Each plugin is self-contained
- No side effects outside plugin scope
- Clear input/output contracts
- Independent testing

**2. Composability**:

- Plugins can be combined freely
- Pipeline phases are composable
- Registry supports multiple plugin types
- No hidden dependencies between plugins

**3. Extensibility**:

- New plugins via inheritance
- No modification of core code
- Plugin metadata for discovery
- Lifecycle hooks for customization

**4. Separation of Concerns**:

```python
# ✅ GOOD: Clear separation
# base.py - Plugin interface
# column.py - Column-specific logic
# frame.py - Frame-specific logic
# registry.py - Registration logic
# lifecycle.py - State management

# ❌ BAD: Everything in one file
# plugins.py - 2000+ lines mixing all concerns
```

### Performance & Efficiency

**Lazy by Default**:

```python
# ✅ GOOD: Lazy until needed
class SchemaValidator:
    def validate(self, df: pl.DataFrame, lazy: bool = True):
        lf = df.lazy() if isinstance(df, pl.DataFrame) else df
        # ... build expression graph ...
        return lf if lazy else lf.collect()

# ❌ BAD: Eager everywhere
class SchemaValidator:
    def validate(self, df: pl.DataFrame):
        df = df.collect()  # Premature materialization
```

**Batch Operations**:

```python
# ✅ GOOD: Apply all transformations at once
exprs = [
    pl.col("age").cast(pl.Int64).alias("age"),
    pl.col("name").str.to_uppercase().alias("name"),
    pl.col("email").str.strip_chars().alias("email"),
]
lf = lf.with_columns(exprs)  # Single pass

# ❌ BAD: Multiple passes
lf = lf.with_columns(pl.col("age").cast(pl.Int64))
lf = lf.with_columns(pl.col("name").str.to_uppercase())
lf = lf.with_columns(pl.col("email").str.strip_chars())
```

**Avoid Unnecessary Copies**:

```python
# ✅ GOOD: Modify in place (LazyFrame is cheap)
lf = lf.with_columns(expr)  # Returns new LazyFrame (no copy)

# ✅ GOOD: Share references
context.data = lf  # Reference, not copy

# ❌ BAD: Explicit copies
df_copy = df.clone()  # Unnecessary for LazyFrame
```

**Cache Plugin Lookups**:

```python
# ✅ GOOD: Lookup once, cache result
class ColumnParsingPhase:
    def execute(self, context: PipelineContext):
        # Cache plugin references
        plugins = {
            name: context.registry.column_parsers.get(name)
            for name in needed_plugins
        }

        for col_name, col_schema in context.schema.columns.items():
            for parser_spec in col_schema.parsers:
                plugin = plugins[parser_spec.name]  # Cached
                # ... use plugin ...

# ❌ BAD: Lookup every time
for col_name, col_schema in context.schema.columns.items():
    for parser_spec in col_schema.parsers:
        plugin = context.registry.column_parsers.get(parser_spec.name)  # Repeated
```

### Type Safety

**Use Type Hints Everywhere**:

```python
# ✅ GOOD: Complete type hints
def register(self, plugin: T) -> None:
    """Register a plugin instance."""
    if not isinstance(plugin, self.plugin_type):
        raise TypeError(f"Expected {self.plugin_type}, got {type(plugin)}")

# ❌ BAD: Missing type hints
def register(self, plugin):  # What type?
    self._plugins[plugin.name] = plugin
```

**Generic Types for Reusability**:

```python
# ✅ GOOD: Generic base class
TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')

class BasePlugin(ABC, Generic[TInput, TOutput]):
    @abstractmethod
    def execute(self, input_data: TInput, **kwargs) -> TOutput:
        pass

# ✅ GOOD: Concrete specialization
class ColumnPlugin(BasePlugin[pl.Expr, pl.Expr]):
    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        # Type checker knows this must return pl.Expr
```

**Runtime Validation**:

```python
# ✅ GOOD: Validate at boundaries
def __call__(self, column: pl.Expr, **kwargs) -> pl.Expr:
    if not isinstance(column, pl.Expr):
        raise TypeError(f"Expected pl.Expr, got {type(column)}")

    result = self.execute(column, **kwargs)

    if not isinstance(result, pl.Expr):
        raise TypeError(f"Plugin must return pl.Expr")

    return result
```

### Error Handling

**Explicit is Better Than Implicit**:

```python
# ✅ GOOD: Specific exceptions with context
class ValidationError(NycteaError):
    def __init__(
        self,
        message: str,
        *,
        column: str | None = None,
        phase: str | None = None,
        errors: pl.DataFrame | None = None
    ):
        super().__init__(message)
        self.column = column
        self.phase = phase
        self.errors = errors

raise ValidationError(
    "Email validation failed",
    column="email",
    phase="column_checks",
    errors=error_df
)

# ❌ BAD: Generic exception
raise ValueError("Validation failed")  # No context
```

**Fail Fast**:

```python
# ✅ GOOD: Validate early
def register(self, plugin: T) -> None:
    if plugin.name in self._plugins:
        raise ValueError(f"Plugin '{plugin.name}' already registered")

    self._plugins[plugin.name] = plugin

# ❌ BAD: Fail later
def register(self, plugin: T) -> None:
    self._plugins[plugin.name] = plugin  # Silently overwrites
```

### Testing Guidelines

**Unit Tests First**:

```python
# ✅ GOOD: Test each component independently
class TestColumnParser:
    def test_purity_validation(self):
        parser = TrimParser()
        result = parser(pl.col("name"))
        assert isinstance(result, pl.Expr)

    def test_rejects_impure_expression(self):
        parser = BadParser()
        with pytest.raises(ValueError, match="forbidden columns"):
            parser(pl.col("name").add(pl.col("other")))
```

**Integration Tests for Workflows**:

```python
# ✅ GOOD: Test full pipeline
class TestPipeline:
    def test_full_validation_workflow(self):
        schema = SchemaModel.from_dict(...)
        registry = MasterRegistry()
        # ... register plugins ...

        result = schema.validate(df, registry)

        assert result.errors is not None
        assert len(result.data) == expected_rows
```

### Code Organization

**One Class Per File** (for large classes):

```
plugins/
├── base.py              # BasePlugin, PluginMetadata (related)
├── column.py            # ColumnPlugin, ColumnParser, ColumnCheck
├── frame.py             # FramePlugin, FrameParser, FrameCheck
├── reader.py            # ReaderPlugin
└── registry.py          # PluginRegistry, MasterRegistry
```

**Group Related Functionality**:

```
engine/
├── pipeline.py          # ValidationPipeline, PipelinePhase
├── phases.py            # All 11 concrete phase implementations
├── context.py           # PipelineContext
└── streaming.py         # StreamingValidator
```

**Explicit Exports**:

```python
# ✅ GOOD: Explicit __all__
__all__ = [
    "BasePlugin",
    "PluginMetadata",
    "ColumnPlugin",
    "ColumnParser",
    "ColumnCheck",
]

# ❌ BAD: Import * with no __all__
from .base import *  # Unclear what's public
```

______________________________________________________________________

## Core Class Hierarchy

```
BasePlugin (ABC)
├── ColumnPlugin (enforce single-column purity)
│   ├── ColumnParser (transformations)
│   └── ColumnCheck (validations)
├── FramePlugin (enforce shape preservation)
│   ├── FrameParser (transformations)
│   └── FrameCheck (validations)
└── ReaderPlugin (format-specific readers)

ValidationPipeline
├── phases: list[PipelinePhase]
├── add_phase(phase, after=None)
├── remove_phase(name)
└── execute(context) → PipelineContext

PipelinePhase (ABC)
├── execute(context) → PipelineContext (abstract)
└── can_skip(context) → bool

PluginRegistry<T>
├── register(plugin: T)
├── get(name: str) → T
└── get_by_tag(tag: str) → list[T]

MasterRegistry
├── column_parsers: PluginRegistry[ColumnParser]
├── column_checks: PluginRegistry[ColumnCheck]
├── frame_parsers: PluginRegistry[FrameParser]
├── frame_checks: PluginRegistry[FrameCheck]
└── readers: PluginRegistry[ReaderPlugin]
```

## Implementation Phases

### Phase 1: Plugin Foundation (Days 1-5)

**Goal**: Establish base classes for all plugins with strict validation

**Critical Files**:

- `src/nyctea/plugins/__init__.py` - Package initialization
- `src/nyctea/plugins/base.py` - BasePlugin, PluginMetadata
- `src/nyctea/plugins/column.py` - ColumnPlugin, ColumnParser, ColumnCheck
- `src/nyctea/plugins/frame.py` - FramePlugin, FrameParser, FrameCheck
- `src/nyctea/plugins/reader.py` - ReaderPlugin base
- `tests/unit/plugins/test_*.py` - Unit tests for each plugin type

**Key Features**:

1. **BasePlugin (ABC)**:

    - Generic `BasePlugin[TInput, TOutput]`
    - `metadata: PluginMetadata` (name, version, description, tags)
    - `execute(input, **kwargs) -> output` (abstract)
    - `validate_args(**kwargs)` (abstract)

1. **ColumnPlugin**:

    - Enforces single-column purity via `__call__` wrapper
    - `_validate_input()`: Checks `column.meta.root_names()` has exactly 1 column
    - `_validate_output()`: Ensures output references same column as input
    - `_validate_signature()`: Checks `execute()` has `column` as first param

1. **FramePlugin**:

    - Configurable: `preserve_columns`, `preserve_rows`
    - `_validate_output()`: Enforces shape preservation rules
    - Captures input shape before execution, validates after

1. **ReaderPlugin**:

    - `supports_format(path)` (abstract)
    - `_validate_path()`: Ensures file exists
    - Integration with SchemaModel for synonym handling

**Validation Strategy**:

- **Registration-time**: Signature validation via `inspect`
- **Runtime**: Purity/shape validation via wrappers
- **Type-safety**: Generic types `BasePlugin[TInput, TOutput]`

______________________________________________________________________

### Phase 2: Plugin Registry (Days 6-10)

**Goal**: Type-safe registry with metadata and lifecycle management

**Critical Files**:

- `src/nyctea/plugins/registry.py` - PluginRegistry, MasterRegistry
- `src/nyctea/plugins/decorators.py` - Decorator adapters for functional style
- `src/nyctea/plugins/lifecycle.py` - Plugin state management
- `tests/integration/test_registry.py` - Registry integration tests

**Key Features**:

1. **PluginRegistry<T>**:

    - Generic over plugin type
    - `register(plugin: T)`: Type-safe registration with collision detection
    - `get(name: str) -> T`: Name-based lookup
    - `get_by_tag(tag: str) -> list[T]`: Tag-based discovery
    - Internal indexing: `_plugins` dict, `_tags` dict

1. **MasterRegistry** (Pydantic model):

    - One `PluginRegistry` per plugin type
    - Type-safe registration methods
    - Replaces current `FunctionRegistry`

1. **Decorator Adapters**:

    - `@registry.column_parser(name, description, tags)`

    - Wraps functions in anonymous plugin classes

    - Maintains functional API ergonomics

    - Example:

        ```python
        @registry.column_parser(name="trim")
        def trim(col: pl.Expr) -> pl.Expr:
            return col.str.strip_chars()
        ```

1. **PluginLifecycle**:

    - States: REGISTERED → VALIDATED → ACTIVE → DISABLED/ERROR
    - Validation hooks
    - Error tracking

______________________________________________________________________

### Phase 3: Validation Pipeline (Days 11-17)

**Goal**: Replace monolithic `validate()` with customizable pipeline

**Critical Files**:

- `src/nyctea/engine/pipeline.py` - Pipeline core classes
- `src/nyctea/engine/phases.py` - Concrete phase implementations (11 phases)
- `src/nyctea/engine/context.py` - PipelineContext dataclass
- `tests/integration/test_pipeline.py` - Full pipeline tests

**Key Features**:

1. **PipelineContext** (dataclass):

    - Shared state passed through all phases
    - Input: `data`, `schema`, `registry`, `coerce_strategy`, `error_report_config`
    - Tracking: `original_nulls`, `coercion_failures`, `check_failures`, `nullified_counts`
    - Output: `errors`, `report`

1. **PipelinePhase** (ABC):

    - `name: str`, `phase_type: PhaseType`
    - `execute(context) -> PipelineContext` (abstract)
    - `can_skip(context) -> bool` (optional conditional execution)

1. **ValidationPipeline**:

    - `phases: list[PipelinePhase]`
    - `add_phase(phase, after=None)`: Insert phase at position
    - `remove_phase(name)`: Remove by name
    - `reorder_phase(name, after=None, before=None)`: Move phase
    - `execute(context) -> PipelineContext`: Run all phases in order

1. **Standard Phases** (11 total):

    - `ColumnResolutionPhase`: Synonym mapping
    - `NullCountingPhase`: Track original nulls
    - `FrameParsingPhase`: Apply frame parsers
    - `ColumnParsingPhase`: Apply column parsers
    - `CoercionPhase`: Type coercion (skippable if `coerce=false`)
    - `FrameCheckPhase`: Frame validations
    - `ColumnCheckPhase`: Column validations + auto-inject `non_null`
    - `ErrorReportingPhase`: Build error DataFrame
    - `NullificationPhase`: Lenient behavior (if `coerce_strategy="null_on_failure"`)
    - `FinalNullableCheckPhase`: Validate nullable constraints
    - `ReportGenerationPhase`: Build ValidationReport

1. **Factory**:

    - `create_default_pipeline() -> ValidationPipeline`: Standard 11-phase pipeline
    - Users can customize returned pipeline before execution

**Migration from Current**:

- Current `validate()` becomes thin wrapper over pipeline
- Extract each section into dedicated phase class
- Maintain exact same validation logic, just reorganized

______________________________________________________________________

### Phase 4: Schema Integration (Days 18-22)

**Goal**: Add OOP validation methods to SchemaModel

**Critical Files**:

- `src/nyctea/schema/model.py` - Enhanced SchemaModel with validate()
- `src/nyctea/schema/validator.py` - SchemaValidator class
- `src/nyctea/schema/profiles.py` - Profile strategy pattern
- `tests/integration/test_schema_validate.py` - End-to-end validation tests

**Key Features**:

1. **SchemaModel.validate()**:

    - Primary API: `schema.validate(df, registry, **kwargs) -> ValidationResult`
    - Delegates to `SchemaValidator`
    - Kwargs: `coerce_strategy`, `error_report`, `lazy`

1. **SchemaValidator**:

    - `__init__(schema, registry, pipeline)`
    - `validate(df, **kwargs) -> ValidationResult`
    - `customize_pipeline() -> ValidationPipeline`: Get copy for customization
    - Handles LazyFrame conversion, row indexing, final collect

1. **SchemaModel.create_validator()**:

    - Factory method: `schema.create_validator(registry, pipeline=None) -> SchemaValidator`

    - Allows users to customize pipeline before validation

    - Example:

        ```python
        validator = schema.create_validator(registry)
        validator.pipeline.add_phase(CustomPhase(), after="coercion")
        result = validator.validate(df)
        ```

1. **Profile Strategies**:

    - Convert current profile logic to Strategy pattern
    - `ProfileStrategy` ABC with `resolve_on_failure(col_schema) -> str`
    - Implementations: `StrictProfile`, `CleanProfile`, `AuditProfile`
    - Factory: `get_profile_strategy(profile: ValidationProfile) -> ProfileStrategy`

1. **Configuration**:

    - `NycteaConfig` Pydantic model for global settings
    - Load from env vars, config files, or explicit
    - Settings: `default_lazy`, `default_coerce_strategy`, `log_level`, `max_error_rows`, etc.

______________________________________________________________________

### Phase 5: Reader Plugins (Days 23-25)

**Goal**: Plugin-based data ingestion system

**Critical Files**:

- `src/nyctea/plugins/readers/csv.py` - CSVReader plugin
- `src/nyctea/plugins/readers/parquet.py` - ParquetReader plugin
- `src/nyctea/ingest/factory.py` - ReaderFactory
- `tests/integration/test_readers.py` - Reader plugin tests

**Key Features**:

1. **CSVReader** (concrete ReaderPlugin):

    - Supports `typed` parameter (schema dtypes vs strings)
    - Synonym handling via `_build_dtype_overrides()`
    - Uses `infer_schema=False` for untyped mode
    - `supports_format()`: `.csv`, `.tsv`, `.txt`

1. **ParquetReader** (concrete ReaderPlugin):

    - Native type reading
    - Multi-file support
    - `supports_format()`: `.parquet`

1. **ReaderFactory**:

    - `read(path, schema, format=None, lazy=True, **kwargs)`
    - Auto-detection: Iterate registered readers, call `supports_format()`
    - Explicit format override via `format` param

1. **Migration**:

    - Replace `src/nyctea/ingest/readers.py` functions with plugins
    - Update `__init__.py` to export factory methods
    - Maintain functional API for backward compatibility (0.1.x)

______________________________________________________________________

### Phase 6: Production Features (Days 26-28)

**Goal**: Error handling, logging, observability, performance

**Critical Files**:

- `src/nyctea/exceptions.py` - Exception hierarchy
- `src/nyctea/observability.py` - Pipeline observers, metrics
- `src/nyctea/config.py` - NycteaConfig model
- `src/nyctea/engine/streaming.py` - StreamingValidator

**Key Features**:

1. **Exception Hierarchy**:

    - `NycteaError` (base)
    - `PluginError` → `RegistrationError`
    - `ValidationError` (with column, phase, errors context)
    - `PipelineError` (with phase, context)
    - Rich error messages with actionable suggestions

1. **Observability**:

    - `PipelineObserver` protocol:
        - `on_phase_start(phase, context)`
        - `on_phase_end(phase, context, metrics)`
        - `on_pipeline_complete(context, duration)`
    - `LoggingObserver`: Log to standard logger
    - `PhaseMetrics`: duration, rows processed/modified, errors found
    - Pluggable observers for custom metrics

1. **Performance**:

    - Lazy evaluation by default
    - Minimal `.collect()` calls
    - Cache plugin lookups
    - Profile hot paths and optimize
    - `StreamingValidator` for large datasets:
        - Batch processing
        - Generator-based iteration
        - Memory-efficient validation

1. **Configuration Management**:

    - `NycteaConfig.from_env()`: Environment variables
    - `NycteaConfig.from_file(path)`: YAML/JSON config
    - Global defaults with per-validation overrides

______________________________________________________________________

### Phase 7: Testing & Documentation (Days 29-30)

**Goal**: Comprehensive tests, migration guide, updated docs

**Critical Files**:

- `tests/unit/plugins/test_*.py` - Plugin unit tests
- `tests/integration/test_*.py` - Integration tests
- `tests/performance/test_*.py` - Performance benchmarks
- `docs/migration_v0.1_to_v0.2.md` - Migration guide
- `docs/architecture.md` - Architecture documentation
- `examples/custom_plugins/` - Plugin examples

**Testing Strategy**:

1. **Unit Tests**:

    - Each plugin base class
    - Registry operations
    - Phase implementations
    - Validator methods

1. **Integration Tests**:

    - Full pipeline execution
    - Schema validation end-to-end
    - Reader plugins with real files
    - Custom pipeline configurations

1. **Performance Tests**:

    - Benchmark against v0.1
    - Large dataset validation
    - Streaming validation
    - Plugin overhead measurement

1. **Documentation**:

    - Migration guide from v0.1 to v0.2
    - Architecture overview with diagrams
    - Plugin development tutorial
    - Custom pipeline examples
    - API reference updates

______________________________________________________________________

## Implementation Order

### Week 1: Foundation

- Days 1-5: Plugin base classes + tests
- Days 6-10: Plugin registry + decorators

### Week 2: Core Refactor

- Days 11-17: Validation pipeline + 11 phases

### Week 3: Integration

- Days 18-22: Schema integration + validator
- Days 23-25: Reader plugins

### Week 4: Production

- Days 26-28: Error handling, logging, performance
- Days 29-30: Testing, docs, examples

______________________________________________________________________

## API Design Examples

### 1. Basic Validation (Schema-Centric)

```python
from nyctea.schema.model import SchemaModel
from nyctea.plugins.registry import MasterRegistry

# Setup
schema = SchemaModel.from_yaml("schema.yaml")
registry = MasterRegistry()
# ... register built-in plugins ...

df = pl.read_csv("data.csv")

# Validate
result = schema.validate(df, registry)

print(f"Valid rows: {len(result.data)}")
if result.errors:
    print(result.errors)
```

### 2. Custom Pipeline

```python
# Create validator with custom pipeline
validator = schema.create_validator(registry)

# Remove coercion phase
validator.pipeline.remove_phase("coercion")

# Add custom phase after parsing
validator.pipeline.add_phase(
    MyCustomPhase(),
    after="column_parsing"
)

# Validate
result = validator.validate(df)
```

### 3. Custom Plugin Registration

```python
from nyctea.plugins.column import ColumnCheck
from nyctea.plugins.base import PluginMetadata
import polars as pl

class EmailValidator(ColumnCheck):
    def __init__(self):
        metadata = PluginMetadata(
            name="email",
            description="Validate email addresses",
            tags=["validation", "string"]
        )
        super().__init__(metadata)

    def execute(self, column: pl.Expr, *, strict: bool = True) -> pl.Expr:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return column.str.contains(pattern)

    def validate_args(self, **kwargs) -> None:
        if 'strict' in kwargs and not isinstance(kwargs['strict'], bool):
            raise TypeError("'strict' must be bool")

# Register
registry.register_column_check(EmailValidator())

# Use in schema
schema = SchemaModel.from_dict({
    "columns": {
        "email": {
            "dtype": "Utf8",
            "checks": [{"name": "email", "args": {"strict": True}}]
        }
    }
})
```

### 4. Functional-Style Registration (Decorator)

```python
from nyctea.plugins.decorators import PluginDecorator

decorators = PluginDecorator(registry)

@decorators.column_parser(name="trim", description="Remove whitespace")
def trim(col: pl.Expr) -> pl.Expr:
    return col.str.strip_chars()

@decorators.column_check(name="positive", tags=["numeric"])
def is_positive(col: pl.Expr) -> pl.Expr:
    return col.gt(0)
```

______________________________________________________________________

## Migration Strategy (v0.1 → v0.2)

Since this is version 0.1 (no backward compatibility needed), we can do a clean redesign:

1. **Keep Old API Temporarily** (0.1.x):

    - Maintain functional `validate()` function
    - Keep old `FunctionRegistry`
    - Add deprecation warnings

1. **Introduce New API** (0.2.0):

    - Add `schema.validate()` method
    - Add plugin system
    - Add customizable pipeline
    - Update all examples

1. **Remove Old API** (0.3.0):

    - Remove functional `validate()`
    - Remove old `FunctionRegistry`
    - OOP-only architecture

**For immediate 0.2.0 release**, we'll ship only the new API since backward compatibility isn't required.

______________________________________________________________________

## Critical Design Decisions

1. **API Style**: ✅ Schema-centric (`schema.validate(df)`)
1. **Plugin Discovery**: ✅ Explicit registration (decorators)
1. **Backward Compatibility**: ✅ Not required (v0.1)
1. **Pipeline Extensibility**: ✅ Fully customizable (add/remove/reorder)
1. **Validation Enforcement**: ✅ Runtime via wrappers (purity, shape)
1. **Type Safety**: ✅ Generics + runtime validation
1. **Registry Architecture**: ✅ Type-safe generic registries

______________________________________________________________________

## Success Criteria

- [ ] All plugin base classes implemented with strict validation
- [ ] Registry system type-safe and fully tested
- [ ] Full 11-phase pipeline with customization support
- [ ] `schema.validate(df)` API functional
- [ ] All built-in parsers/checks migrated to plugins
- [ ] Reader plugin system working for CSV/Parquet
- [ ] Comprehensive test suite (>90% coverage)
- [ ] Performance at least as good as v0.1
- [ ] Complete documentation with examples
- [ ] Migration guide for future users

______________________________________________________________________

## File Structure (Post-Refactor)

```
src/nyctea/
├── schema/
│   ├── model.py          # SchemaModel with validate()
│   ├── validator.py      # SchemaValidator
│   └── profiles.py       # Profile strategies
├── plugins/
│   ├── base.py           # BasePlugin, PluginMetadata
│   ├── column.py         # ColumnPlugin, ColumnParser, ColumnCheck
│   ├── frame.py          # FramePlugin, FrameParser, FrameCheck
│   ├── reader.py         # ReaderPlugin base
│   ├── registry.py       # PluginRegistry, MasterRegistry
│   ├── decorators.py     # Decorator adapters
│   ├── lifecycle.py      # Plugin lifecycle management
│   └── readers/
│       ├── csv.py        # CSVReader
│       └── parquet.py    # ParquetReader
├── engine/
│   ├── pipeline.py       # ValidationPipeline, PipelinePhase
│   ├── phases.py         # 11 concrete phase implementations
│   ├── context.py        # PipelineContext
│   ├── validate.py       # Legacy compat wrapper (deprecate later)
│   └── streaming.py      # StreamingValidator
├── ingest/
│   └── factory.py        # ReaderFactory
├── observability.py      # PipelineObserver, metrics
├── exceptions.py         # Exception hierarchy
├── config.py             # NycteaConfig
└── utils/
    └── logger.py         # Logging utilities
```

______________________________________________________________________

## Next Steps

Once this plan is approved:

1. **Sprint 1** (Days 1-5): Implement plugin base classes
1. **Sprint 2** (Days 6-10): Build registry system
1. **Sprint 3** (Days 11-17): Refactor pipeline
1. **Sprint 4** (Days 18-22): Schema integration
1. **Sprint 5** (Days 23-28): Production features
1. **Sprint 6** (Days 29-30): Testing and docs

Total estimated effort: **30 development days** (~6 weeks at 5 days/week)
