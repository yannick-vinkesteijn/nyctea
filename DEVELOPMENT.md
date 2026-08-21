# Development Guide

Quick reference for common development tasks.

## Prerequisites

- **uv** - Fast Python package manager (required)
- **just** - Command runner (optional, but recommended)

### Install Prerequisites

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install just (optional)
brew install just  # macOS
# or
cargo install just  # via Rust
```

## Quick Start

### With Just (Recommended)

```bash
# Setup development environment
just setup

# Run tests
just test

# Run pre-commit hooks
just pre-commit

# Run full CI simulation
just ci

# See all commands
just --list
```

### Without Just

```bash
# Setup development environment
uv sync --group dev --group test --group docs

# Run tests
uv run pytest tests/

# Run pre-commit hooks
uv run pre-commit run --all-files

# Run full CI simulation
./scripts/ci-full.sh
```

## Common Workflows

### Before Committing

```bash
# Quick validation
just check
# or
uv run pre-commit run && uv run pytest tests/ -q
```

### Before Pushing

```bash
# Full CI simulation (recommended!)
just ci
# or
./scripts/ci-full.sh
```

This runs:
- ✓ Linting (Ruff)
- ✓ Tests on all Python versions (3.10-3.14)
- ✓ Type checking (mypy)
- ✓ Build validation

### Testing Across Python Versions

```bash
just test-all
# or
./scripts/test-all-versions.sh
```

### Building Package

```bash
just build-check
# or
uv build && uv run twine check dist/*
```

## Available Commands

Run `just --list` to see all available commands:

- **Development**
  - `just setup` - Install development environment
  - `just clean` - Clean build artifacts
  - `just update-deps` - Update dependencies

- **Testing**
  - `just test` - Run tests
  - `just test-cov` - Run tests with coverage
  - `just test-all` - Test all Python versions
  - `just test-quick` - Quick test run

- **Code Quality**
  - `just lint` - Run linter
  - `just format` - Format code
  - `just fix` - Auto-fix linting issues
  - `just typecheck` - Run type checker
  - `just secure` - Security scan
  - `just pre-commit` - Run all pre-commit hooks

- **CI Simulation**
  - `just ci` - Run full CI locally
  - `just ci-lint` - Simulate lint job
  - `just ci-test` - Simulate test job
  - `just ci-build` - Simulate build job

- **Building**
  - `just build` - Build package
  - `just build-check` - Build and verify

- **Documentation**
  - `just docs-build` - Build docs
  - `just docs-serve` - Serve docs locally

- **Utilities**
  - `just check` - Quick pre-commit validation
  - `just validate` - Full validation
  - `just status` - Show project status

## Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`. They include:

- Trailing whitespace removal
- End-of-file fixing
- YAML validation
- Ruff formatting
- Ruff linting
- uv-secure vulnerability scanning
- And more...

To skip hooks (not recommended):
```bash
git commit --no-verify
```

## Testing

### Run Specific Tests

```bash
# Single test file
just test tests/test_exceptions.py

# Single test
just test tests/test_exceptions.py::test_nyctea_error_is_base

# With verbose output
just test -v

# With coverage
just test-cov
```

### Coverage Reports

After running `just test-cov`, view coverage:
- Terminal: Shown in output
- HTML: Open `htmlcov/index.html`
- XML: `coverage.xml` (for CI)

## Security Scanning

```bash
# Run uv-secure vulnerability scan
just secure

# Configuration in pyproject.toml:
# [tool.uv-secure.maintainability_criteria]
```

## CI/CD

### Local CI Simulation

Before pushing, always run:

```bash
just ci
```

This ensures your changes will pass GitHub Actions.

### GitHub Actions Workflows

- **CI** - Runs on every push/PR to main
  - Lint job (Ruff)
  - Test job (Python 3.10-3.14)
  - Type check job (mypy)

- **Build** - Runs on every push/PR to main
  - Build job (package build + twine check)
  - Install-test job (verify wheel installation)

- **Pre-commit** - Runs on every push/PR to main
  - All pre-commit hooks

## Troubleshooting

### "Command not found: pytest"

```bash
# Ensure virtual environment is set up
just setup
# or
uv sync --group test
```

### Tests fail on specific Python version

```bash
# Install specific Python version
uv python install 3.13

# Test with that version
uv run --python 3.13 pytest tests/
```

### Pre-commit hooks modified files

This is normal. The hooks auto-fix issues (formatting, trailing whitespace).
Simply stage the changes and commit again:

```bash
git add -u
git commit -m "your message"
```

## Links

- [Justfile](justfile) - All available commands
- [Scripts](scripts/) - Helper scripts for CI simulation
- [Pre-commit Config](.pre-commit-config.yaml) - Pre-commit hook configuration
- [GitHub Actions](.github/workflows/) - CI/CD workflows
