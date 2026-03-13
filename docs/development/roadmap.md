---
icon: lucide/map
---

# Roadmap

!!! info "v0.2.0 status"
    The OOP plugin system and pipeline scaffolding are in place. Three phases are working (`ColumnResolutionPhase`, `ColumnParsingPhase`, `ColumnCheckPhase`). The remaining work below completes the pipeline and stabilises the public API.

---

## v0.2.0 Backlog

### Step 1: Batch `ColumnCheckPhase` collects

**Status:** :material-check-circle: Done

Check expressions are built as boolean mask columns on the LazyFrame. Zero collects in the check phase.

---

### Step 2: `CoercionPhase` + `on_failure` refactor

**Status:** :material-check-circle: Done

Type casting with per-column `on_failure` behavior. Always casts with `strict=False`; pre-null masks track coercion-introduced nulls. The validator enforces `on_failure=raise` columns post-collect.

Replaced `ValidationProfile` (`strict`/`clean`/`audit`) and `coerce_strategy` parameter with a unified `on_failure` field at schema and column level. See [ADR: on_failure](decisions/adr-on-failure.md).

=== "on_failure: raise (default)"

    ```python
    schema = SchemaModel.from_dict({"coerce": True, "on_failure": "raise", ...})
    schema.validate(df, registry)  # raises on any cast failure
    ```

=== "on_failure: null"

    ```python
    schema = SchemaModel.from_dict({"coerce": True, "on_failure": "null", ...})
    schema.validate(df, registry)  # failed casts become null
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

Set failing values to null for columns with `on_failure='null'`. Depends on coercion and error reporting being done first.

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

- [x] Coercion — on_failure raise + null
- [x] on_failure resolution (schema default, column override, nullable guard)
- [ ] Lenient nullification (`on_failure='null'` for check failures)
- [ ] Error reporting modes — summary, rows, cells
- [ ] Frame-level plugins
- [ ] Schema loading from YAML
- [ ] Edge cases — empty DataFrames, missing columns, ambiguous synonyms
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
| `ColumnCheckPhase` | :material-check-circle: Done |
| `CoercionPhase` | :material-check-circle: Done |
| `NullificationPhase` | :material-clock-outline: Todo |
| `ErrorReportingPhase` | :material-clock-outline: Todo |
| `FrameParserPhase` | :material-clock-outline: Todo |
| `FrameCheckPhase` | :material-clock-outline: Todo |

---

## API & usability

- **Pipeline customization**: stable public API for adding, removing, and reordering phases
- **Schema from YAML**: complete YAML schema loading with validation
- **Streaming support**: ensure all phases work with `sink_parquet` / `scan_parquet`
