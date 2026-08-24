---
icon: lucide/git-pull-request
---

# Contributing

How to propose a change, from an idea to a merged PR.

## 1. Open an issue first

For anything beyond a typo fix, open an issue before writing code.
It gets the change agreed on before time goes into it, and it becomes the reference the PR closes.
Existing issues, including closed ones, are the best guide to the project's actual defect and design history.
They carry more detail than the changelog and are searchable by symptom.

Skip the issue for trivial fixes such as a broken link or a typo.
Open the PR directly for those.

## 2. Branch and commit

Branch from `main`, named `<type>/<issue>-<slug>`.
For example `fix/7-nullable-enforcement` or `ci/17-pypi`.
`docs/`, `ci/`, and `fix/` are the types in use; use whichever fits.

Keep commits scoped and the message short.
One line describing what changed is enough.
The why belongs in the PR description or the issue.

## 3. Before committing

```bash
just check          # pre-commit + quick tests + type check
# or
uv run pre-commit run --all-files && uv run pytest tests/ -q
```

## 4. Before opening the PR

```bash
just ci              # full local CI simulation
# or
uv run pytest tests/ -v
uv run pre-commit run --all-files
```

Run the docs build if you touched anything under `docs/` or `zensical.toml`.
The build's issue count does not catch a broken mkdocstrings config, an image path, or a dead nav target, so check the rendered output rather than trusting that the count is unchanged.

```bash
just docs-build
```

## 5. Open the PR

The template covers what's expected.
Link the issue it closes, note any breaking changes, and list what was tested.
Label the PR (`bug`, `enhancement`, `documentation`, `breaking`) so it lands in the right section of the release notes; see [Releasing](RELEASING.md#the-actual-flow) for how those get generated.
For breaking changes, also add one to `docs/releases/breaking-changes.md`.

Copilot's automated review runs on push.
Read every finding and reply on the thread with a verdict. Say it's fixed, or give a stated reason it's wrong.
Don't resolve a thread silently.
Copilot is usually right, but it never returns a clean review, so treat "changes recommended" as its default state rather than a blocker in itself.
A quiet thread does not mean the code went unreviewed.

### Merging

`main` requires a PR and one approving review.
GitHub's Copilot reviewer only ever submits `COMMENTED`, never `APPROVED`, so it can never satisfy that gate on its own.
Merging as the repo owner needs the ruleset bypass.
That is expected behavior here, not a workaround to avoid.

## Design principles

The full rules live in `.claude/CLAUDE.md` at the repo root.
That file is the single source of truth for coding conventions, and it is what an AI agent working on this repo actually reads.
What follows is a summary, not a substitute for it.

- **Lazy by default.** Use `scan_*` and `LazyFrame` at every entry point. Call `.collect()` only at the final step or where the operation strictly requires it. This is not a style preference: see [#11](https://github.com/yannick-vinkesteijn/nyctea/issues/11) for what happens when it slips.
- **Batch Polars expressions.** Use one `with_columns` or `select` per phase. Never loop over columns in Python.
- **Type everything.** Use native hints such as `str | None` and `list[int]`, not `typing` equivalents. Do not use `from __future__ import annotations`. See [breaking changes](../releases/breaking-changes.md) for why that specific rule is hard here, not just a preference.
- **Fail loud.** Silent fallbacks are how [#7](https://github.com/yannick-vinkesteijn/nyctea/issues/7) and its follow-ups stayed hidden. Validate at construction time, not deep inside a pipeline phase.
- **Inheritance for the validator hierarchy, composition for the pipeline.** `PipelinePhase` objects compose into `ValidationPipeline`. `ColumnValidator` and `FrameValidator` subclasses define structure. Methods stay functionally pure: pass data through arguments and return values, and don't accumulate state on `self`.
- **Reusable code lives in `src/nyctea/utils/`.** Never duplicate it into a submodule. Every other submodule stays self-contained with a clear boundary.
- **Verify Polars against the docs, not memory.** The API moves, and a plausible-looking method may be deprecated or renamed. This project uses the [Polars MCP](https://mcp.pola.rs) for exactly this reason where it's available.

## Code style

```bash
uv run ruff check src/ tests/     # lint
uv run ruff format src/ tests/    # format
uv run ty check src/nyctea        # types
```

All three also run inside `Pre-commit`, described below, so this is for fast local iteration rather than a separate gate.
Docstrings follow the Google style.
Test only this project's own code, not the behavior of a library it depends on.

## Testing

```bash
uv run pytest tests/ -v
```

Write tests as plain functions, not classes, and use fixtures for shared setup.
Keep each test to one behavior.
Test files mirror the `src/` structure under `tests/`.

## Documentation

Built with [Zensical](https://zensical.org/).
Locally:

```bash
just docs-build    # or: uv run --group docs zensical build
just docs-serve    # or: uv run --group docs zensical serve
```

See [Writing documentation](writing-docs.md) for docstring and page conventions.
The build's issue count does not catch a broken mkdocstrings config, an image path, or a dead nav target.
Check the rendered output after a nav or asset change instead of trusting that the count is unchanged.

## AI-assisted contributions

AI coding assistants, Claude Code included, are part of the normal workflow here, both for implementation and for review through GitHub Copilot's automated PR review described above.
That doesn't change how a contribution is judged.

1. **You own your commits.** Whether or not an assistant helped write a line, the person who commits it is responsible for it. Read it, understand it, and verify it before it goes in. "the AI wrote it" is not a defense for a bug or a bad design call.
2. **Same triage, same process, no exception.** An AI-assisted PR or commit is reviewed, tested, and merged exactly like any other. It does not get a lighter pass because a tool helped write it, and it does not get a heavier one either.
3. **Disclose substantial AI involvement** in the PR description when an assistant wrote most of a non-trivial change. This is not a confession, just context for the reviewer.
4. **License compliance.** If a tool's output includes identifiable third-party code, verify it is compatible with this project's MIT license and attribute it.

This project's own agent instructions live in `.claude/CLAUDE.md` at the repo root.
Keep it short and specific. It should state hard rules the agent cannot infer from the code itself, such as using `uv` instead of `pip` or the Polars laziness rules above, not read like a tutorial.
A rule that just restates what the linter already enforces doesn't need to be there.

## CI

`CI` and `Build` run on every PR and every push to `main`. `Pre-commit` runs on the PR only, not on push, so it never fails the way it did before: rerunning `no-commit-to-branch` against a commit that is already on `main` fails by definition, since the commit reviewed on the PR is the same one that lands on `main`, there is nothing new to check on push.

| Workflow | Job(s) | What it checks |
| --- | --- | --- |
| `Pre-commit` | `pre-commit` | Formatting, linting (`ruff`), types (`ty`), lockfile freshness, `uv audit`, docs formatting, `.github/workflows/*` schema |
| `CI` | `test` | pytest, matrix across Python 3.11 to 3.14 |
| `Build` | `build`, `install-test` | Wheel builds, passes `twine check`, installs into a clean environment, imports successfully |

There is no separate lint or type-check job in `CI`.
Those run once, inside `Pre-commit`.
If you're about to add a check, confirm an existing hook doesn't already cover it first.
`ci.yaml` used to carry a duplicate `ruff` job and a `mypy` job that was never installed and could never fail.

Two more workflows run on their own schedule rather than per PR.
`Documentation` deploys the site on push to `main`.
`Dependency Audit` scans weekly via `uv audit` and opens an upgrade PR on findings.
`Draft Release` and `Publish to PyPI` run on tag push and release publish; see [Releasing](RELEASING.md).

## Environment

- **[`uv`](https://docs.astral.sh/uv/)** is required. It manages Python versions and dependencies.
- **[`just`](https://github.com/casey/just)** is an optional command runner. `just --list` shows every recipe. `just setup` installs the dev environment and pre-commit hooks.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv
just setup                                        # or: uv sync --all-groups --all-extras
```

See `justfile` for the full command list.
