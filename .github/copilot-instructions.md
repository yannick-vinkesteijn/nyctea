# Copilot Instructions for Nyctea

Nyctea is a Polars-based data validation library with a validator architecture.
Source lives in `src/nyctea/`.

## Basic rules

- **Never commit or push.** The developer reviews and commits everything themselves.
  Stage or edit files and draft commit messages, but do not run `git commit` or `git push`.
- Keep responses short and precise. Ask for clarification when unsure rather than guessing.
- Write plainly: no em dashes, emoji, hype adjectives, or filler.

## Common mistakes to avoid

- Do NOT call `.collect()` prematurely. Keep frames lazy until the final step or when
  an operation strictly requires it.
- Do NOT use `DataFrame` as input/output when `LazyFrame` works.
- Do NOT process large files in memory. Use `scan_parquet`, `sink_parquet`, `scan_csv`
  for out-of-core workflows.
- Do NOT loop over rows or columns. Batch operations into single `with_columns`/`select` calls.
- Do NOT use `print()` -- use `get_logger(__name__)` from `nyctea.utils.logger`.
- Do NOT put shared utilities inside submodules; put them in `src/nyctea/utils/`.
- Do NOT use `typing.Optional`, `typing.List`, etc. Use native hints (`str | None`, `list[int]`).
- Do NOT use `from __future__ import annotations`.

## Design

- OOP throughout: inheritance for the validator hierarchy (`Validator` -> `ColumnValidator`
  -> `ColumnParser`/`ColumnCheck`, and the equivalent `FrameValidator` branch), composition
  for the pipeline (`ValidationPipeline` containing `PipelinePhase` objects).
- Methods should be functionally pure: pass data via arguments and return values, don't
  store intermediate state on `self`.

## Polars

- Polars is the default data framework. Design for out-of-core data.
- Use `LazyFrame` and `scan_*` as entry points; only `collect()` at the final step or
  when required by the operation.
- Batch Polars operations: combine multiple column expressions into a single
  `with_columns` or `select` call rather than looping.
- Verify Polars expressions and methods against
  https://docs.pola.rs/api/python/stable/reference/index.html when writing new Polars
  code; the API moves fast, don't rely on memory for it.
- This repo's `.mcp.json` configures a `polars` MCP server. Prefer it over a raw docs
  fetch when it's available.

## Python

- Target Python 3.11+. Native type hints only.
- Use `TYPE_CHECKING` blocks only to break circular imports for type annotations.
  Keep runtime imports inline.
- Google-style docstrings.

## Project tooling

- Use `uv` as the package manager and task runner (`uv run pytest`, `uv run ruff check .`).
- All tool configuration lives in `pyproject.toml`.
- Use `ty` for type checking, never mypy.
- Use `just` recipes for common tasks (`just test`, `just lint`, `just pre-commit`).

## GitHub project

- Track Nyctea work in the
  [Nyctea backlog](https://github.com/users/yannick-vinkesteijn/projects/2).
- Create implementation branches from the issue with GitHub's Development
  linkage, for example `gh issue develop <number> --base main --name <branch>`.
- Open pull requests from the linked development branch and add the pull request
  to the project. Do not use `Closes`, `Fixes`, or `Resolves` references in pull
  request bodies.
- Move the pull request and its linked issues to `In review` when the pull request is
  ready for review. Let the Development linkage update the issue when the pull
  request merges.

## Testing

- `pytest`, plain functions rather than test classes; use fixtures for shared setup.
- Only test our own code, not functionality from external packages.
- Test files mirror the source structure under `tests/` (`src/nyctea/foo/bar.py` ->
  `tests/foo/test_bar.py`).
- Keep tests simple and focused on one behaviour per test.

## Agent working documents

Working documents (plans, design notes, reviews, handover notes) go in `.agents/`,
gitignored and never committed, not in `docs/` (the deployed site). Anything meant to
be public goes in a GitHub issue, or in `docs/development/decisions/` as a dated ADR
once implemented.

## Working from the plan

- Read the newest `.agents/plan/` document and the newest `.agents/memory/` handover
  before starting work. The plan's "Order of work" is the ordering authority. If another
  document disagrees with it, the plan wins and the other document needs fixing.
- Do the current step, not the next one. If the work would touch something the current
  step does not name, stop and ask rather than folding it in.
- Report a step's exit criterion even when it fails. A step that did not deliver what it
  promised is a signal to stop and reconsider, not to keep building.
- Before reversing a decision recorded in `.agents/design/`, say so explicitly and get
  agreement. Do not quietly build the other thing.
- Record rejected options and why, not just the chosen one. A decision with only a
  conclusion cannot be audited later; one that names its alternatives can be rechecked
  when the constraints change.
- Prefer a test to a sentence. A rule in prose drifts as context is compacted; a rule in
  `tests/` fails loudly. `tests/test_import_structure.py` is the model.

## Documentation

- Update `docs/user-guide/` for user-facing behaviour changes (public API, validator
  interface, schema syntax) and `docs/api/` when adding, removing, or renaming public
  classes or functions.
- Write plainly: full sentences, no em dashes, no colon-then-fragment constructions.

## Safety: destructive operations

Never run a destructive or irreversible command without asking first: force-pushing,
`git reset --hard`, `rm -rf`, deleting branches/tags, dropping a database/table, or
touching production or shared infrastructure. Prefer the safe form first (dry-run
flags, `git status`) and explain the command before the developer runs it.
