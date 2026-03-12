# ADR: Composable Phase-Based Validation Pipeline

**Status:** Accepted
**Date:** 2026-03-12

---

## Context

Nyctea needs to orchestrate a fixed sequence of operations: resolve column names, parse values, coerce types, run checks, report errors, nullify failures, and generate a report. The question is how to structure this logic.

Two approaches exist in the codebase right now:

- **System A** (`engine/validate.py`): A single `validate()` function. About 250 lines of imperative code with a hardcoded pipeline order and private helper functions. Feature-complete and working.
- **System B** (`engine/pipeline.py` + `engine/phases.py`): A `ValidationPipeline` containing `PipelinePhase` objects. Each phase is a class that declares its dependencies and implements `execute()`. Currently incomplete.

---

## Decision

We are replacing System A with System B: a composable, phase-based pipeline.

The pipeline is the primary execution model. Each pipeline step is a `PipelinePhase` subclass that:
- declares its `name`, `phase_type`, and `dependencies`
- implements `execute(context) -> context`
- optionally implements `can_skip(context) -> bool`

The `PipelineContext` is the single shared state object passed between phases. It carries the `LazyFrame`, schema, registry, and accumulated results.

---

## Rationale

### Why not stick with the monolithic function?

System A works, but has hard limits:

- **No user extension.** Users cannot add a custom phase (e.g., an audit logger, a masking step, a row deduplication pass) without forking the function.
- **Ordering is implicit.** The 13-step sequence is embedded in one function body. A reader must trace control flow to understand dependencies.
- **Testing is coarse.** You can only test the function end-to-end. Individual steps cannot be unit-tested in isolation.
- **Reuse is impossible.** `_apply_column_parsers` and friends are module-private. They cannot be composed differently.

### Why phases?

Each `PipelinePhase` is independently testable, replaceable, and composable:

```python
# Users can add phases without modifying library code
validator.pipeline.add_phase(AuditPhase(), after="column_checks")
```

Dependency declarations make ordering explicit and enforceable:

```python
class ColumnCheckPhase(PipelinePhase):
    def __init__(self):
        super().__init__(
            name="column_checks",
            phase_type=PhaseType.CHECKING,
            dependencies=["column_parsing"],  # explicit
        )
```

`can_skip()` lets phases opt out cleanly when they have nothing to do, keeping the pipeline fast for simple schemas.

### Why keep the PipelineContext as a shared state object?

Passing `context` through each phase avoids a long argument list and allows phases to accumulate results (e.g., `check_failures`, `coercion_failures`, `nullified_counts`) without coupling each phase to the return signature of the previous one.

Context is mutable shared state, which requires discipline. The rule: **phases only write to context fields they own** (e.g., `ColumnCheckPhase` writes `context.check_failures`, not `context.data`).

### Why not a functional pipeline (list of callables)?

A list of `Callable[[LazyFrame], LazyFrame]` is simpler for transformation steps. It breaks down for reporting phases that need to accumulate metadata (error counts, null stats) alongside the frame. `PipelineContext` unifies both concerns.

---

## Consequences

**Good:**
- Users can insert, remove, and reorder phases without modifying library code.
- Each phase is independently testable.
- Pipeline configuration can be inspected and logged (phase names, dependency graph).
- Custom validation profiles can be implemented as different phase configurations.

**Trade-offs:**
- More code than a single function for equivalent behaviour.
- Phase dependency validation adds startup cost (negligible in practice).
- Mutable context requires discipline. Phases must not write to fields they don't own.

---

## Migration from System A

System A (`engine/validate.py`) remains the reference implementation during migration. Each phase in System B must produce identical output to its corresponding step in System A before System A is removed.

Target phase mapping:

| System A step               | System B phase              |
|-----------------------------|-----------------------------|
| `resolve_column_names`      | `ColumnResolutionPhase` ✅  |
| `_count_original_nulls`     | tracked in context           |
| `_apply_frame_parsers`      | `FrameParserPhase` (todo)   |
| `_apply_column_parsers`     | `ColumnParsingPhase` ✅     |
| `_apply_coercion`           | `CoercionPhase` (todo)      |
| `_apply_frame_checks`       | `FrameCheckPhase` (todo)    |
| `_collect_column_checks`    | `ColumnCheckPhase` ✅ (partial) |
| `_build_error_report`       | `ErrorReportingPhase` (todo)|
| `_apply_lenient_checks`     | `NullificationPhase` (todo) |
| `_check_final_nullable`     | part of `NullificationPhase`|
| report generation           | `_build_report()` (stub)    |
