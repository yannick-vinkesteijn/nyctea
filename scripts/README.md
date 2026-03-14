# Development Scripts

Helper scripts for local development and CI simulation.

## Scripts

### `test-all-versions.sh`
Tests the package across all supported Python versions (3.10-3.14), mimicking the GitHub Actions test matrix.

```bash
./scripts/test-all-versions.sh
```

### `ci-lint.sh`
Runs linting checks (Ruff) exactly as GitHub Actions does.

```bash
./scripts/ci-lint.sh
```

### `ci-build.sh`
Simulates the GitHub Actions build workflow:
- Builds the package
- Validates with twine
- Tests installation and import

```bash
./scripts/ci-build.sh
```

### `ci-full.sh`
Runs all CI workflows locally (lint, test, type-check, build).
**Run this before pushing to ensure CI will pass!**

```bash
./scripts/ci-full.sh
```

### `release.sh`
Handles version bumping and release workflow.

```bash
./scripts/release.sh
```

## Usage with Just

These scripts are integrated into the [justfile](../justfile). Recommended workflow:

```bash
# Quick development cycle
just check          # Run pre-commit + quick tests + typecheck

# Before committing
just pre-commit     # Run all pre-commit hooks

# Before pushing
just ci             # Simulate full CI locally

# Test all Python versions
just test-all       # Runs test-all-versions.sh

# Full validation (everything)
just validate       # Clean + setup + CI + build
```

## Requirements

- `uv` - Python package manager
- Python 3.10-3.14 (automatically installed by uv)
- `just` (optional, for using the justfile)

Install just: `brew install just` (macOS) or see https://github.com/casey/just
