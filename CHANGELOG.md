# Changelog

All notable changes to Nyctea are recorded here.
This file is maintained by hand and is the canonical account of what changed in each release.
The auto-generated notes on each [GitHub Release](https://github.com/yannick-vinkesteijn/nyctea/releases) are a raw list of merged pull requests.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) as described in [Releasing](docs/development/RELEASING.md#versioning).

## [Unreleased]

### Added

- Frame-level parsers and checks are now wired into the pipeline through `FrameParsingPhase` and `FrameCheckPhase`, instead of being accepted by the schema and silently ignored (#8).
- `SchemaModel.streaming_row_threshold` controls whether validation's internal aggregate collects use Polars' streaming engine. Above the threshold they stream, which roughly halves peak memory on large data. Below it they use the default engine, since streaming's fixed setup cost is not worth paying on small data. A `LazyFrame` input always streams, since its size is unknown without collecting (#11).
- `AggregateEngine` type alias, `Literal["in-memory", "streaming"]`.

### Changed

- The per-phase metrics block no longer collects when no observers are registered (#11).
- Result models now live in `nyctea.engine.results`, leaving one canonical implementation after the legacy validation module was removed. Public imports from `nyctea` are unchanged (#12, #43).
- Public APIs are layered: common workflow objects come from `nyctea`, schema configuration models from `nyctea.schema`, and extension types from `nyctea.validators` (#43).

### Removed

- The untested legacy validation system: `nyctea.functions`, `FunctionRegistry`, and the standalone `nyctea.engine.validate.validate()` function. Use `Registry`, `ValidatorDecorator`, and `SchemaModel.validate()` instead. Removing the legacy registry also resolves its decorator typing defect (#42, #43).
- The Titanic-specific `register_titanic_validators()` helper from the library API. The example owns its validators directly now (#43).

### Fixed

- Declaring two checks with the same name on one column now raises `PipelineError` instead of silently dropping the first one. `check_masks`, `result.errors`, and the report stats are all keyed on `(column, check name)`, so the second declaration overwrote the first and orphaned its mask, removing that check from both reporting and enforcement. A column declaring `between(0, 5)` under `on_failure: "raise"` would accept a value of `30` and report the dataset 100% valid. See [breaking changes](docs/releases/breaking-changes.md).
- `on_failure` is now enforced for check failures, not only for coercion-introduced nulls. `raise` actually raises, and `null` actually nulls the failing value. Both were previously silent: the failure was recorded in `result.errors` while execution continued with the bad value still in the output (#9).
- `_build_report` no longer reports every dataset as 100% valid. It is built from the same masks as `result.errors`, so `report` and `errors` agree (#6).
- Per-column check failure counts in the report sum each check's failures rather than counting distinct failing rows, matching the totals in `errors`. A row failing two checks now contributes two failures in both places (#6).

## [0.2.0b2] - 2026-08-24

### Fixed

- Dead `DEVELOPMENT.md` link in the PyPI README, the same root cause as the earlier logo path fix (#29).

## [0.2.0b1] - 2026-08-24

First published release, and the first under the validator-based architecture.
Everything before this was unreleased: the repository carried a `0.1.0` version string from its initial commit but was never tagged or published, so the entries below are measured against that unreleased state rather than against anything a user could have installed.
See [breaking changes](docs/releases/breaking-changes.md).

### Added

- OOP validator architecture: `Validator` -> `ColumnValidator` -> `ColumnParser`/`ColumnCheck`.
- `Registry` for registering and looking up parsers and checks by name.
- `ValidationPipeline` composed of `PipelinePhase` objects, with `PipelineContext` carrying shared state across phases.
- Pipeline phases: `ColumnResolutionPhase`, `ColumnParsingPhase`, `CoercionPhase`, `ColumnCheckPhase`.
- `ErrorReportConfig` with three modes: `summary`, `rows`, `cells`.
- `on_failure` at schema and column level, taking `raise`, `null`, or `ignore`.
- Per-column `coerce` override of the schema default.
- Column synonym resolution with ambiguity detection.
- Decorator API, `@decorators.column_check` and `@decorators.column_parser`, for defining validators as plain functions.
- Built-in parsers `strip`, `lower`, `upper`, `to_int`, `to_float`, and built-in checks `min_value`, `between`, `in_set`, `unique`.
- Targeted error collection: only the mask and the relevant columns are collected, never the full frame.
- Pre-null masks for distinguishing coercion-introduced nulls from nulls already present in the input.
- Documentation site built with Zensical.
- Trusted publishing to PyPI over OIDC, with a human-reviewed draft release step (#17, #18, #22).

### Changed

- `validate()` keeps the data lazy throughout. Error reporting and the report still use targeted collects, so the pipeline is not collect-free, but the data itself is never materialised.
- Renamed the `plugins` module to `validators`.
- Minimum supported Python raised to 3.11.

### Fixed

- `nullable: false` is now enforced. This changes behaviour for schemas that never declared `nullable: true` (#7).
- `on_failure: "ignore"` on a non-nullable column now reports the null in `errors` under the check name `not_null`, instead of passing it through silently.
- Generated mask columns (`__notnull__*`, `__check__*`, `__pre_null__*`) now raise on collision with a real input column, instead of overwriting it and dropping it from the output.
- Removed `from __future__ import annotations` across the engine, validator, and schema modules (#13).
- CI: dropped Python 3.10 from the test matrix, fixed lint violations, and repaired the stale registry import in the build smoke test (#14, #15, #16).

### Removed

- `strict`, `clean`, and `audit` validation profiles, replaced by `on_failure`.
- The `coerce_strategy` parameter, replaced by per-column `on_failure`.

[Unreleased]: https://github.com/yannick-vinkesteijn/nyctea/compare/v0.2.0b2...HEAD
[0.2.0b2]: https://github.com/yannick-vinkesteijn/nyctea/compare/v0.2.0b1...v0.2.0b2
[0.2.0b1]: https://github.com/yannick-vinkesteijn/nyctea/releases/tag/v0.2.0b1
