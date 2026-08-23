# Changelog

All notable changes to Nyctea are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] (v0.2.0)

### Added

- OOP validator architecture with `Validator`, `ColumnValidator`, `ColumnParser`, `ColumnCheck` hierarchy
- `Registry` for registering and looking up parsers and checks by name
- `ValidationPipeline` with composable `PipelinePhase` objects
- Pipeline phases: `ColumnResolutionPhase`, `ColumnParsingPhase`, `ColumnCheckPhase`, `CoercionPhase`
- `ErrorReportConfig` with three modes: `summary`, `rows`, `cells`
- `on_failure` field at schema and column level (`raise`, `null`, `ignore`)
- Per-column `coerce` override (column-level `coerce=True/False` overrides schema default)
- Column synonym resolution with ambiguity detection
- Decorator API (`@decorators.column_check`, `@decorators.column_parser`) for functional-style validators
- Built-in parsers: `strip`, `lower`, `upper`, `to_int`, `to_float`
- Built-in checks: `min_value`, `between`, `in_set`, `unique`
- Targeted error collection (only collects mask and relevant columns, never full data)
- Pre-null masks for tracking coercion-introduced nulls
- `PipelineContext` for shared state across phases
- Documentation site with MkDocs Material

### Fixed

- `nullable: false` is now enforced. See `docs/development/breaking-changes.md`; this changes behavior for schemas that did not declare `nullable: true`.
- `on_failure: "ignore"` on a non-nullable column now reports the null in `errors` under check name `not_null` instead of silently passing it through.
- Generated mask columns (`__notnull__*`, `__check__*`) now raise if they collide with a real input column, instead of overwriting it and dropping it from the output.

### Changed

- `validate()` keeps the data lazy. Aggregates for error reporting and the report still use targeted collects, so the pipeline is not collect-free.
- Error reporting uses targeted collects instead of collecting the full DataFrame.
- Replaced `ValidationProfile` with unified `on_failure` field.

### Removed

- `strict` / `clean` / `audit` validation profiles (replaced by `on_failure`)
- `coerce_strategy` parameter (replaced by per-column `on_failure`)

## [0.1.0] - 2025-01-01

### Added

- Initial release with functional validation engine
- Schema definition via `SchemaModel.from_dict()`
- Column-level dtype validation and coercion
- Function registry for parsers and checks
- Basic error reporting (summary mode only)
