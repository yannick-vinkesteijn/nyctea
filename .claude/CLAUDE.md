# Claude Instructions for Nyctea

Nyctea is a Polars-based data validation library with a plugin architecture. Source lives in `src/nyctea/`.

## Common mistakes to avoid
- Do NOT call `.collect()` prematurely. Keep frames lazy until the final step or when an operation strictly requires it.
- Do NOT use `DataFrame` as input/output when `LazyFrame` works.
- Do NOT process large files in memory. Use `scan_parquet`, `sink_parquet`, `scan_csv` for out-of-core workflows.
- Do NOT loop over rows or columns. Batch operations into single `with_columns`/`select` calls.
- Do NOT use `print()` -- use `get_logger(__name__)`.
- Do NOT put shared utilities inside submodules.
- Do NOT use `typing.Optional`, `typing.List`, etc. Use native hints.

## Design

- Nyctea uses OOP: inheritance for the plugin hierarchy (`BasePlugin` -> `ColumnPlugin` -> `ColumnParser`/`ColumnCheck`), composition for the pipeline (`ValidationPipeline` containing `PipelinePhase` objects). Follow these patterns for new code.
- Classes define structure and interface via inheritance, but methods should be functionally pure -- pass data via arguments and return values, don't store intermediate state on `self`.

## Polars

- Polars is the default data framework. Design for out-of-core data.
- Use `LazyFrame` and `scan_*` as entry points; only `collect()` at the final step or when required by the operation.
- Support streaming/larger-than-RAM files via `sink_parquet`, `scan_parquet`, etc.
- Batch Polars operations: combine multiple column expressions into a single `with_columns` or `select` call rather than looping.
- ALWAYS verify Polars expressions and methods against https://docs.pola.rs/api/python/stable/reference/index.html when writing new Polars code. Do not rely on memory for Polars API.
- Polars evolves fast. Do not assume deprecated patterns still work. Verify against current docs.

## Python

- Target Python 3.11+. Do not use `from __future__ import annotations`.
- Use `TYPE_CHECKING` blocks only to break circular imports for type annotations. Keep runtime imports inline.
- Use native type hints (`str | None`, `list[int]`, etc.) instead of `typing` equivalents.
- Use `logging` via `get_logger(__name__)` from `nyctea.utils.logger`, never `print()`.
- Use Google-style docstrings.

## Project tooling

- Always use `uv` as the package manager and task runner.
- All settings and tool configuration live in `pyproject.toml`.
- Run commands with `uv run` (e.g., `uv run pytest`, `uv run ruff check .`).
- Use `ty` for type checking and enforcement.
- Use `just` recipes for common tasks.

## Code organization

- `src/nyctea/utils/` contains generic, reusable functions and helpers used across the project.
- Do not put reusable code inside submodules if it will be shared elsewhere.
- Each submodule should be self-contained with clear boundaries.

## Testing

- Use `pytest` for all tests.
- Write tests as plain functions, not inside classes. Use fixtures for shared setup.
- Only test our own code, not functionality from external packages/libraries.
- Test files mirror the source structure under `tests/`.
- Keep tests simple and focused on one behavior per test.

## Documentation

- Update `docs/guides/` when changing user-facing behaviour (public API, plugin interface, schema syntax).
- Update `docs/api/` when adding, removing, or renaming public classes or functions.
- The `docs/development/` folder is for developer and contributor documentation (contributing guide, roadmap, releasing). Update it when development processes change.
- Write documentation that is concise and direct. Use short sentences. Avoid filler phrases and decorative punctuation such as em dashes.
