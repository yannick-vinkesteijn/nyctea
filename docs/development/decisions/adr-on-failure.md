# ADR: Replace `profile` with `on_failure` at schema and column level

**Date:** 2026-03-13

---

## Context

The schema has a `profile` field (`strict`, `clean`, `audit`) that controls failure behavior, plus a per-column `on_failure` field (`raise`, `null`). The `validate()` call also accepts a `coerce_strategy` runtime parameter (`strict`, `null_on_failure`). This creates three overlapping knobs for one concern.

Problems:
- `clean` is not self-explanatory.
- `audit` is just `strict` with more reporting, not a failure-handling mode.
- `coerce_strategy` as a runtime param duplicates what the schema should declare.
- Users must learn both `profile` and `on_failure` to understand behavior.

## Decision

Replace `profile` and `coerce_strategy` with a single `on_failure` field at both schema and column level.

**Values:** `raise` | `null` | `ignore`

| `on_failure` | Coercion fails | Check fails |
|---|---|---|
| `raise` | Error, stop | Error, stop |
| `null` | Value becomes null | Value becomes null |
| `ignore` | Value becomes null (forced by dtype) | Value kept, failure reported |

**Resolution order:**
1. Column `on_failure` if set explicitly.
2. Schema `on_failure` as default.
3. Guard: `on_failure=null` requires `nullable=True`. Non-nullable columns fall back to `raise`.

**Schema example:**
```yaml
on_failure: ignore
coerce: true
columns:
  patient_id:
    dtype: Utf8
    nullable: false
    on_failure: raise    # override: must be clean
  age:
    dtype: Int64
    nullable: true       # inherits "ignore" from schema
  temperature:
    dtype: Float64
    nullable: true
    on_failure: "null"   # override: nullify bad temps
```

## Why `ignore` nullifies coercion failures

A string `"abc"` cannot exist in an Int64 column. Polars enforces typed columns. `ignore` means "don't modify valid-typed data" but coercion nulls are physically unavoidable. This is documented, not configurable.

## What gets removed

- `ValidationProfile` type (`strict`, `clean`, `audit`).
- `SchemaModel.profile` field.
- `SchemaModel.resolve_on_failure()` method (replaced by simpler resolution).
- `coerce_strategy` parameter on `validate()` and `PipelineContext`.

## What gets added

- `SchemaModel.on_failure: OnFailureBehavior` (default `raise`).
- `OnFailureBehavior` extended to `Literal["raise", "null", "ignore"]`.
- `SchemaModel.resolve_on_failure(col_name)` simplified: column explicit > schema default > nullable guard.

## Consequences

- One concept to learn instead of three.
- `coerce` stays independent: it controls whether casting happens, not what happens when it fails.
- Reporting configuration (`summary`, `rows`, `cells`) stays on `ErrorReportConfig`, separate from failure handling.
- Breaking change from v0.1.x `profile` field. Acceptable for v0.2.0.
