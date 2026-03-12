---
icon: lucide/map
---

# Roadmap

!!! info "v0.2.0 status"
    The OOP plugin system and pipeline scaffolding are in place. Three phases are working (`ColumnResolutionPhase`, `ColumnParsingPhase`, `ColumnCheckPhase`). The remaining work below completes the pipeline and stabilises the public API.

---

## v0.2.0 Backlog

### Step 1: Batch `ColumnCheckPhase` collects

**Status:** :material-wrench: Pending — performance bug

[`engine/phases.py`](../../src/nyctea/engine/phases.py) calls `.collect()` once per check per column. A schema with 10 columns and 3 checks each causes ~30 collects. It should be 1.

!!! bug "Impact"
    For large schemas this serialises all Polars parallelism and dramatically slows validation.

**Fix:** build all check expressions into a single `select` and collect once.

---

### Step 2: `CoercionPhase`

**Status:** :material-clock-outline: Pending

Type casting with `strict` and `null_on_failure` modes. Ported from System A (`engine/validate.py`). Must run after parsing, before checks, so checks operate on typed data.

=== "strict mode"

    ```python
    schema.validate(df, registry, coerce_strategy="strict")
    # raises on any cast failure
    ```

=== "null_on_failure mode"

    ```python
    schema.validate(df, registry, coerce_strategy="null_on_failure")
    # failed casts become null, validation continues
    ```

---

### Step 3: `ErrorReportingPhase`

**Status:** :material-clock-outline: Pending

Replaces the `_build_errors()` stub in `schema/validator.py`. Produces row-level and cell-level error records in all three modes.

!!! warning "Currently broken"
    `_build_errors()` returns an empty DataFrame regardless of failures. Nothing in the current pipeline surfaces per-row error detail.

| Mode | Output |
|------|--------|
| `summary` | column · check · count |
| `rows` | + list of failing row indices |
| `cells` | + actual failing values per row |

---

### Step 4: Fix `_build_report()`

**Status:** :material-clock-outline: Depends on Step 3

!!! warning "Currently broken"
    `_build_report()` computes `valid_rows` by summing failure counts (wrong: counts duplicates across checks on the same row). The `columns` dict is always empty.

Fix after `ErrorReportingPhase` is in place so the report has real data.

---

### Step 5: `NullificationPhase`

**Status:** :material-clock-outline: Depends on Steps 2 + 3

Set failing values to null for columns with `on_failure='null'` (lenient / `clean` profile mode). Depends on coercion and error reporting being done first.

---

### Step 6: `FrameParserPhase` / `FrameCheckPhase`

**Status:** :material-clock-outline: Pending

Frame-level plugin execution. Required to complete the plugin hierarchy and unblock the Titanic example.

---

### Step 7: Remove `engine/validate.py` (System A)

**Status:** :material-clock-outline: Depends on Steps 1–6

Once all pipeline phases cover System A's features, delete the standalone `validate()` function. Until then, keep it as the reference implementation.

!!! tip "Why keep it?"
    System A is fully working and serves as the ground-truth oracle. Each new phase should produce identical output to its System A counterpart before System A is removed.

---

### Step 8: Tests for all new phases

**Status:** :material-clock-outline: Ongoing alongside Steps 1–6

Critical paths currently uncovered:

- [ ] Coercion — strict + null-on-failure
- [ ] Lenient nullification (`on_failure='null'`)
- [ ] Error reporting modes — summary, rows, cells
- [ ] Frame-level plugins
- [ ] Schema loading from YAML
- [ ] Edge cases — empty DataFrames, missing columns, ambiguous synonyms
- [ ] Validation profiles — `clean`, `audit`
- [ ] Pipeline observer notifications

---

### Step 9: Merge to main

**Status:** :material-clock-outline: Depends on Steps 1–8

PR from `v0.2.0` to `main` once the full backlog is complete.

---

## Background: performance

The biggest wins come from reducing premature `.collect()` calls that break Polars lazy evaluation.

| Optimisation | Reduction |
|---|---|
| Batch null counting | Per-column loops → 1 `select` |
| Batch check failure counting | N×M collects → 1 collect |
| Defer row counting | After every phase → end only |
| Frame plugin shape validation | Always → only when `preserve_rows=True` |

For a schema with 10 columns and 3 checks each, this reduces from ~68 collects to ~5.

---

## Background: planned pipeline phases

| Phase | Status |
|---|---|
| `ColumnResolutionPhase` | :material-check-circle: Done |
| `ColumnParsingPhase` | :material-check-circle: Done |
| `ColumnCheckPhase` | :material-alert-circle: Partial (collect batching needed) |
| `CoercionPhase` | :material-clock-outline: Todo |
| `NullificationPhase` | :material-clock-outline: Todo |
| `ErrorReportingPhase` | :material-clock-outline: Todo |
| `FrameParserPhase` | :material-clock-outline: Todo |
| `FrameCheckPhase` | :material-clock-outline: Todo |

---

## API & usability

- **Pipeline customization**: stable public API for adding, removing, and reordering phases
- **Schema from YAML**: complete YAML schema loading with validation
- **Streaming support**: ensure all phases work with `sink_parquet` / `scan_parquet`
