# ADR: Validation API Design and Library Comparison

**Status:** Accepted
**Date:** 2026-03-12
**Library versions verified:** Pandera 0.29.0 · Patito 0.8.6 · Dataframely 2.7.0 · Great Expectations 1.15.0

---

## Context

Nyctea's public validation API is `schema.validate(df, registry)`. The schema is the entry point: it owns the pipeline and drives execution. This document explains the design by comparing it with the dominant alternatives in the Python/Polars ecosystem.

---

## Alternatives Considered

### Pandera (v0.29.0)

Pandera is the most established Python data validation library. It supports pandas, Polars, Spark, and Ibis. Validation is declared through class-based schemas (`DataFrameSchema`, `pa.DataFrameModel`) or check decorators.

```python
import pandera.polars as pa

class MySchema(pa.DataFrameModel):
    name: Series[str]
    age: Series[int] = pa.Field(ge=0)

MySchema.validate(df)
```

**Strengths:**
- Mature, well-documented, large community.
- Full Polars support (`pip install 'pandera[polars]'`), including nested List/Array/Struct types.
- `LazyFrame` accepted. Type coercion runs without `.collect()`.
- "Lazy validation" (deferred error collection: gather all failures before raising) is ✅ for Polars.

**Limitations for Nyctea's use case:**
- **Lazy validation ≠ lazy execution.** Pandera's "lazy validation" means deferred error collection, not Polars lazy evaluation. Full data-level validation on a `LazyFrame` requires `PANDERA_VALIDATION_DEPTH=SCHEMA_AND_DATA`, which forces a `collect()`. Schema-only validation is the default.
- **Custom check registration is Polars ❌.** `@extensions.register_check_method()` exists but is explicitly unsupported on the Polars backend (confirmed in the official feature matrix).
- **Parsers are Polars ❌.** Pandera's `Parser` abstraction (runs transformations before checks) is unavailable on the Polars backend. `coerce=True` is the only preprocessing option.
- The internal pipeline is fixed. There is no API to inject, remove, or reorder phases.

Official Pandera Polars backend feature matrix (v0.29.0):

| Feature | Polars |
|---------|--------|
| DataFrameSchema / DataFrameModel validation | ✅ |
| Built-in and custom Checks | ✅ |
| Custom check registration | ❌ |
| Preprocessing with Parsers | ❌ |
| Lazy validation (deferred error collection) | ✅ |
| Dropping invalid rows | ✅ |
| Schema inference / persistence | ❌ |

### Patito (v0.8.6)

Patito provides Polars-first schema validation via Pydantic-style model classes.

```python
import patito as pt

class Product(pt.Model):
    product_id: int = pt.Field(dtype=pl.UInt32, unique=True)
    name: str

Product.validate(df)
```

**Strengths:**
- Extremely clean API. Validation models look like Pydantic models.
- Designed specifically for Polars; no pandas baggage.
- `cast()`, `derive()`, and `fill_null()` methods give a limited transform-before-validate pattern.
- Actively maintained (v0.8.6, February 2026).

**Limitations:**
- `LazyFrame` support exists (`patito.Model.LazyFrame`) but is underdocumented with no streaming capability.
- No plugin registry. Checks are pre-defined field constraints or require subclassing.
- No pipeline customization. Transform and validate are separate method calls, not a unified pipeline.
- No frame-level parsers or checks.
- No coercion strategy control (strict vs lenient).

### Great Expectations (v1.15.0)

GE is an enterprise data quality platform. It separates expectations (schema), validators (execution), and data docs (reporting).

```python
suite = context.add_expectation_suite("my_suite")
validator = context.get_validator(batch_request, expectation_suite_name="my_suite")
validator.expect_column_values_to_not_be_null("name")
results = validator.validate()
```

**Strengths:**
- Very mature enterprise tooling.
- Rich reporting and data docs UI.
- Broad connector ecosystem.

**Limitations:**
- **No Polars support in GX Core 1.x.** The official docs list pandas and Spark only. A community issue requesting Polars support (filed March 2024) was closed as "not planned" in August 2024. The changelog from v1.2.5 to v1.15.0 contains zero Polars-related entries.
- Heavy operational overhead: data contexts, data sources, checkpoints.
- Overkill for library-level validation embedded in a data pipeline.

### Dataframely (v2.7.0)

Dataframely is a Polars-native library focused on typed, reusable DataFrame collections. Maintained by Quantco.

```python
import dataframely as dy

class Users(dy.Collection):
    id: dy.Column[pl.Int64] = dy.Column(primary_key=True)
    name: dy.Column[pl.Utf8]

result = Users.filter(df)  # returns valid rows
```

**Strengths:**
- Polars-only, built with Polars idioms throughout.
- **LazyFrame support since v2.0.0** via a custom Polars plugin. The `eager=False` parameter appends validation to the lazy graph rather than executing immediately:
  ```python
  lf.pipe(MySchema.validate, eager=False)  # validation deferred to collect()
  ```
- Collection model is intuitive for reusable typed frames.
- `filter()` mode returns only valid rows instead of raising.

**Limitations:**
- LazyFrame validation is deferred, not true streaming. Data must still fit in memory at `collect()` time. Single-error reporting in collection-level lazy mode.
- No plugin registry. Rules are declared via `@dy.rule()` decorators on the schema class, not registered externally.
- No parser/transformation layer. Dataframely validates; it does not transform. `cast=True` on validate is the only preprocessing.
- No custom pipeline phases.
- No synonym resolution or coercion strategy control.

---

## Decision

Nyctea is designed for **production data pipelines** where validation, transformation, and error handling are **all part of one configurable pass**. The core design decisions are:

### 1. Schema owns validation: `schema.validate(df, registry)`

Nyctea's `SchemaValidator` explicitly owns a `ValidationPipeline` that the user can customize. This means:
- The schema carries its pipeline configuration.
- Two schemas can have different pipelines (e.g., one for ETL, one for audit).
- The pipeline can be inspected and modified before running.

### 2. Plugins are registered objects, not decorated functions

Pandera, Patito, and Dataframely tie checks to the schema declaration. Nyctea decouples them: checks and parsers live in a `Registry`, schemas reference them by name.

This enables:
- **Shared plugin libraries.** A team registers company-standard checks once and reuses them across many schemas.
- **Runtime registration.** Plugins can be registered based on config files or environment.
- **OOP extension.** Subclassing `ColumnParser` or `ColumnCheck` gives full control over `validate_args()`, metadata, and tagging.
- **Functional extension.** The decorator API (`@decorators.column_check(...)`) matches the ergonomics of Pandera/Patito for simple cases.

Note: Pandera has a `register_check_method()` decorator, but it is explicitly unsupported on the Polars backend as of v0.29.0.

### 3. Parsing is a first-class pipeline phase, not a side effect

None of the alternatives above support a dedicated parse layer on the Polars backend. Pandera has a `Parser` abstraction but it is documented as pandas-only. Patito's `cast()`/`derive()` are separate calls, not a pipeline phase. Dataframely has no transform layer at all.

Nyctea treats parsing and checking as distinct, ordered phases:
- **ETL pipelines.** Normalise strings, coerce types, then check typed values.
- **Clean output.** The validated frame is already transformed and ready to use downstream.
- **Failure handling.** `on_failure` at schema and column level controls what happens when coercion or checks fail: `raise`, `null`, or `ignore`.

### 4. Pipeline is composable, not fixed

The validation pipeline is a sequence of `PipelinePhase` objects that users can add to, remove from, or reorder:

```python
validator.pipeline.add_phase(MaskPIIPhase(), after="column_checks")
validator.pipeline.add_phase(AuditLogPhase(), after="column_checks")
```

None of the compared libraries expose a pipeline API. Pandera, Patito, and Dataframely have fixed internal pipelines. Great Expectations has "checkpoints", but they are heavyweight infrastructure objects, not composable code-level phases.

### 5. Streaming / out-of-core is a first-class concern

All phases operate on `LazyFrame`. `sink_parquet` / `scan_parquet` paths are a design constraint, not an afterthought.

Dataframely's `eager=False` is the closest competitor. It defers validation to `collect()` time, but data must still fit in memory when collected. Nyctea's goal is to keep data lazy through the entire pipeline, including output writes, so datasets larger than RAM can be validated without materialising them.

---

## Trade-offs

| Concern | Nyctea | Pandera 0.29 | Patito 0.8.6 | Dataframely 2.7 | Great Expectations 1.15 |
|---------|--------|-------------|-------------|----------------|------------------------|
| Polars-native | ✅ | Partial (multi-backend) | ✅ | ✅ (Polars-only) | ❌ (no Polars support) |
| LazyFrame support | ✅ | Partial (schema-only by default) | Partial (underdocumented) | ✅ (`eager=False` since v2.0) | ❌ |
| True out-of-core / streaming | ✅ (goal) | ❌ | ❌ | ❌ (deferred, not streaming) | ❌ |
| Plugin registry (Polars) | ✅ | ❌ (pandas only) | ❌ | ❌ | ❌ |
| Composable pipeline phases | ✅ | ❌ | ❌ | ❌ | ❌ |
| Parse + validate in one pass (Polars) | ✅ | ❌ (pandas only) | ❌ | ❌ | ❌ |
| Schema-as-code (class style) | Via dict/YAML | ✅ | ✅ | ✅ | ✅ |
| Maturity / community | Early | High | Medium | Early-medium | High |
| Minimal boilerplate | Medium | Low | Low | Low | High |

Nyctea trades boilerplate for flexibility. For a project that just wants to check a few columns, Patito or Dataframely are simpler. For a production ETL pipeline where you need custom transforms, coercion strategies, custom error reporting, and composable phases, Nyctea's architecture pays off.

---

## Validate Function Signature

The public entry point is:

```python
result = schema.validate(df, registry)
```

The underlying `SchemaValidator.validate()` signature:

```python
def validate(
    self,
    df: pl.DataFrame | pl.LazyFrame,
    *,
    error_report_config: ErrorReportConfig | None = None,
    lazy: bool | None = None,
) -> ValidationResult:
```

Key decisions:
- `df` is positional. It is the only required argument after `self`.
- `registry` is on `self` (set at construction time), not passed per-call. A validator is bound to a registry; swapping registries means creating a new validator.
- Failure handling is on the schema (`on_failure` at schema and column level), not a runtime parameter. See [ADR: on_failure](adr-on-failure.md).
- `error_report_config` controls the shape of the `errors` DataFrame in `ValidationResult`. Defaults to `ErrorReportConfig(mode="summary")`.
- `lazy` overrides `schema.lazy`. By default the output type matches what the schema declares.
- All optional arguments are keyword-only (`*`) to prevent positional coupling as the API evolves.
