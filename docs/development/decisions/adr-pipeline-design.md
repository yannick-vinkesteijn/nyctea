# ADR: Composable Phase-Based Validation Pipeline

**Date:** 2026-03-12

---

## Context

Libraries like Pandera, Patito, and Dataframely give you a fixed pipeline: define a schema, call validate, get errors. You cannot reorder steps, inject custom logic between them, or skip steps you don't need. The pipeline is the library's decision, not yours.

Nyctea takes a different position: **the user decides how validation runs**. The pipeline is composable. Users insert, remove, reorder, and replace phases.

---

## Decision

Validation runs as a sequence of `PipelinePhase` objects. Each phase:

- declares `name`, `phase_type`, and `dependencies`
- implements `execute(context) -> context`
- optionally implements `can_skip(context) -> bool`

Phases communicate through a shared `PipelineContext`. This is a mutable state object carrying the `LazyFrame`, schema, registry, and accumulated results.

```python
# Users control the pipeline
validator.pipeline.add_phase(AuditPhase(), after="column_checks")
validator.pipeline.remove_phase("coercion")
```

---

## Why phases over a monolithic function

The current `validate()` function (~250 lines) works but cannot be extended, reordered, or tested in parts. Phases fix this:

```python
class ColumnCheckPhase(PipelinePhase):
    def __init__(self):
        super().__init__(
            name="column_checks",
            phase_type=PhaseType.CHECKING,
            dependencies=["column_parsing"],  # ordering is explicit
        )
```

- Each phase is independently testable.
- `dependencies` make ordering explicit. No implicit control flow.
- `can_skip()` lets phases opt out when they have nothing to do.

---

## Why a shared context, not a function chain

A `Callable[[LazyFrame], LazyFrame]` chain works for pure transformations. It breaks when phases need to accumulate metadata (error counts, null stats, coercion failures) alongside the frame.

`PipelineContext` carries both. The rule: **phases only write to fields they own**.

```python
# PipelineContext fields and their owners:
#   data (LazyFrame)       - resolution, parsing, coercion, checks
#   check_masks            - column_checks only
#   coercion_failures      - coercion only
#   nullified_counts       - nullification only
#   original_nulls         - null tracking only
```

The `LazyFrame` is a Polars query plan, not materialized data. Passing it between phases is cheap. Users who `.collect()` early own that cost.

---

## Trade-offs

- More code than a single function for equivalent behaviour.
- Mutable shared context requires discipline. The ownership convention above keeps it manageable.
- Phase dependency validation adds negligible startup cost.

---

## Migration

`engine/validate.py` remains the reference implementation. Each phase must produce identical output to its corresponding step before the monolith is removed.

The monolith is removed once all phases below are implemented and integration tests pass against shared fixtures.

| `validate()` step           | Pipeline phase               |
|-----------------------------|------------------------------|
| `resolve_column_names`      | `ColumnResolutionPhase` ✅   |
| `_count_original_nulls`     | tracked in context            |
| `_apply_frame_parsers`      | `FrameParserPhase` (todo)    |
| `_apply_column_parsers`     | `ColumnParsingPhase` ✅      |
| `_apply_coercion`           | `CoercionPhase` (todo)       |
| `_apply_frame_checks`       | `FrameCheckPhase` (todo)     |
| `_collect_column_checks`    | `ColumnCheckPhase` ✅ (partial) |
| `_build_error_report`       | `ErrorReportingPhase` (todo) |
| `_apply_lenient_checks`     | `NullificationPhase` (todo)  |
| `_check_final_nullable`     | part of `NullificationPhase` |
| report generation           | `_build_report()` (stub)     |
