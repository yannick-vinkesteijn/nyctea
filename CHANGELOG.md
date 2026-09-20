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

- Dependency updates come from Dependabot rather than the `Dependency Audit` workflow, which is removed. `.github/dependabot.yml` covers `uv.lock` and the pinned action versions in the workflows. The workflow duplicated Dependabot's security alerts, needed the repository to allow Actions to create pull requests, and failed on that permission even after its audit step was fixed. The `uv-audit` pre-commit hook still runs the same scan locally when the lockfile changes (#64).
- Every built-in phase name now has one definition, in `nyctea.engine.phase_names`. The name was previously hand-written by the phase, by the `dependencies` of phases ordered against it, and by the raise plan that attributes a failure, which is how the raise plan came to report a not-null failure under the wrong phase (#72).
- `CoercionPhase` is no longer forced to run before `ColumnCheckPhase`/`FrameCheckPhase`: a check written against raw string values can now run before coercion, one written against typed values can run after. `PipelinePhase` gained a `pinned` position (`"first"`/`"last"`), independent of `dependencies`, for the two positions that are still fixed: `ColumnResolutionPhase` always first, `NotNullPhase` always last. `ValidationPipeline` rejects any custom phase ordering that violates either (#87).
- The per-phase metrics block no longer collects when no observers are registered (#11).
- Result models now live in `nyctea.engine.results`, leaving one canonical implementation after the legacy validation module was removed. Public imports from `nyctea` are unchanged (#12, #43).
- Public APIs are layered: common workflow objects come from `nyctea`, schema configuration models from `nyctea.schema`, and extension types from `nyctea.validators` (#43).

### Removed

- `preserve_columns` and `preserve_rows` on `FrameValidator`, `FrameParser` and the frame decorators. A validator that declares its own shape contract can always declare a weaker one, and the two registration paths disagreed on the `preserve_rows` default. `preserve_columns` also asserted that the output column set equalled the input's, which rejected a parser adding a derived column while the schema was still satisfied. `FrameParsingPhase` already rejects an output missing a column the schema requires, which is the contract that matters, and dropping `preserve_rows` removes two collects per frame validator. A row count never proved row alignment anyway, since a reordering parser preserves it exactly. `FrameCheckPhase` now discards whatever a check returns, which makes a check structurally unable to change the data, where the flags had been the only thing stopping it (#80).
- `DataValidator` is no longer exported from `nyctea`. `SchemaModel.validate` gained a `pipeline` parameter, so it now covers every run including a customized pipeline, and its loose `**kwargs` is replaced by the real parameters `error_report_config`, `lazy` and `pipeline`. The class remains at `nyctea.engine.validator` (#100).
- `SchemaModel.lazy` and `SchemaModel.streaming_row_threshold`, deprecated in favour of `nyctea.Config`. A schema declaring either is now rejected at construction with an error naming every moved field it found and the `nyctea.Config` call for each, rather than pydantic's generic unknown-field message (#100).
- `import nyctea` no longer configures logging. It attached a `StreamHandler` and set the level to INFO, which wrote Nyctea's records into an application's stderr at a level it had not chosen. Only a `logging.NullHandler` is attached now. `configure_logging` and `NYCTEA_LOG_LEVEL` stay as an opt-in for scripts and the command line (#100).
- The untested legacy validation system: `nyctea.functions`, `FunctionRegistry`, and the standalone `nyctea.engine.validate.validate()` function. Use `Registry`, `ValidatorDecorator`, and `SchemaModel.validate()` instead. Removing the legacy registry also resolves its decorator typing defect (#42, #43).
- The Titanic-specific `register_titanic_validators()` helper from the library API. The example owns its validators directly now (#43).

### Fixed

- A column check that answers once for the whole frame, such as `column.count() >= 5`, is rejected by name. `with_columns` broadcasts a single value over every row, so it read as every row failing and `on_failure="null"` emptied the column over a fact about the frame. Checks combining an aggregate with a per-row operand, such as `column - column.min() < 2` or a window, are unaffected (#74).
- A column check may use a window over the column it checks, such as `column.count().over(column) >= 3` for a group-size rule. The purity rule counted `root_names()` rather than its distinct entries, and a self-referencing window names the same column twice, so it was rejected as referencing two columns. A check referencing a genuinely different column is still rejected (#74).
- A column check whose expression does not evaluate to a boolean is rejected by name. It used to reach aggregation and fail with a Polars cast error naming neither the check nor the column (#74).
- `ValidationPipeline` rejects a phase list that names the same phase twice, in the constructor and in `add_phase`. A name identifies a phase throughout the pipeline, so two phases sharing one made `dependencies`, `add_phase(after=)` and `remove_phase` all resolve to the first and left the second unreachable (#76).
- `Registry.get_by_tag` returns a copy rather than the registry's own tag index. Appending to the result used to register a validator, where `list_all` and `list_names` already copied (#73).
- The `cells` error report no longer fails on a `Binary` column holding bytes that are not valid UTF-8. Values were cast to text, which raised `invalid utf8` and failed the whole report; they are hex-encoded now. Nested dtypes still have no text rendering and are tracked separately in #104 (#75).
- `just build-check` and `scripts/release.sh` could not check a built distribution. The first called `uv run twine check` with twine absent from the project, and the second ran `uv run pip install twine` first, which fails because pip is not in a uv-managed environment. twine is now declared in a `release` dependency group, and the four places that check a distribution all run `uv run --only-group release twine check dist/*`. `--only-group` keeps the check to twine alone: `--group` would also sync the default `dev` group, so on a clean runner it installed 68 packages instead of 22 and could fail over a test or docs dependency unrelated to the artifact. `just setup` and a plain `uv sync` both leave it out, so only a release pays for it and its dependency chain (#66).
- The weekly dependency audit failed before checking anything. `uv export` emits the editable project as `-e .`, which carries no hash, and `pip-audit --require-hashes` refuses a file containing an unhashed entry. The job now runs `uv audit`, which reads `uv.lock` directly, and which the `uv-audit` pre-commit hook already used (#64).
- The Titanic example's `functions.py` used `@frame_parser` without importing it, so the example could not run. Pre-existing, unrelated to the surface freeze, fixed here because it was found while verifying the examples (#100).
- A check or parser whose expression builds but fails on the data now raises `PipelineError` with the underlying Polars exception as its `__cause__`, instead of escaping as a raw Polars exception that `except NycteaError` does not catch. Evaluation happens after every phase has run, so it was outside the pipeline's own error handling (#72).
- An observer that raises can no longer change the outcome of a run. A failure in `on_pipeline_error` used to replace the error it was told about, leaving the caller with the observer's exception and the real one only as `__context__`. Observer failures are logged instead (#72).
- `ValidationPipeline`'s mutation API is now covered: `add_phase` with a conflicting or unknown neighbour, `add_phase` and `remove_phase` during a run, `copy()`, and `PipelinePhase.__repr__`. No behaviour changed, but every one of those paths was public and untested (#68).
- `schema.validate` now raises `ValidationError` when the input does not match the schema's structure, meaning a required column is missing or a name resolves ambiguously, instead of rewrapping it as `PipelineError`. Every other failure of a validation run still raises `PipelineError`, which gained a `column` attribute. Every failure Nyctea raises for a named column now sets it, across the aggregate `on_failure="raise"` paths, the parser and check phases, and internal-column collisions. Schema verification still raises `ConfigurationError` before the run starts. A `ValidationError` raised by a phase now reaches the caller unwrapped, and everything else a phase raises, including from the `can_skip` and `can_change_row_count` hooks, is wrapped as `PipelineError` with the original as its `__cause__`. `can_change_row_count` is now asked on every run rather than only when an observer is attached. A wrapped `PipelineError` keeps the `column` the phase set, while `phase` names the phase that was running. Not-null failures now report `phase="not_null"` rather than `phase="column_checks"`. See [breaking changes](docs/releases/breaking-changes.md) (#72).
- Column parsers that turn non-null input into null now produce a `parse` error with the original failing value, reduce `rows_valid`, obey `on_failure`, and populate `parse_failures`. Reports now also populate `original_null_count` from the resolved input before frame and column transformations. Parser, coercion, and nullability failures are enforced together in pipeline order without a separate nullability collect (#63, #65).
- Frame parsers can no longer remove required schema columns, and Nyctea now rebuilds private row tracking after frame transformations so every error report mode remains available (#62).
- User checks named `coerce` or `not_null` are now rejected in every schema configuration because those names identify built-in failures throughout enforcement and reporting (#71).
- Absent optional columns now skip configured parsers and checks instead of failing with a missing-column error (#59).
- Declaring two checks with the same name on one column now raises `PipelineError` instead of silently dropping the first one. `check_masks`, `result.errors`, and the report stats are all keyed on `(column, check name)`, so the second declaration overwrote the first and orphaned its mask, removing that check from both reporting and enforcement. A column declaring `between(0, 5)` under `on_failure: "raise"` would accept a value of `30` and report the dataset 100% valid. See [breaking changes](docs/releases/breaking-changes.md).
- `on_failure` is now enforced for check failures, not only for coercion-introduced nulls. `raise` actually raises, and `null` actually nulls the failing value. Both were previously silent: the failure was recorded in `result.errors` while execution continued with the bad value still in the output (#9).
- `_build_report` no longer reports every dataset as 100% valid. It is built from the same masks as `result.errors`, so `report` and `errors` agree (#6).
- Per-column check failure counts in the report sum each check's failures rather than counting distinct failing rows, matching the totals in `errors`. A row failing two checks now contributes two failures in both places (#6).
- `on_failure: "null"` is now legal on a non-nullable column, instead of being rejected or silently downgraded to `"raise"`. A resulting not-null violation, whether from a nulled check or a genuinely null source value, is reported rather than raised, the same way `"ignore"` already behaves (#89).

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
