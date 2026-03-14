# Nyctea Development Justfile
# Run `just --list` to see all available commands

set shell := ["bash", "-c"]
set dotenv-load := true

# Default recipe - show available commands
default:
    @just --list

# === Environment Setup ===

# Install development environment and pre-commit hooks
setup:
    uv sync --all-groups --all-extras
    uv run pre-commit install

# Clean build artifacts and caches
clean:
    @echo "Cleaning build artifacts..."
    rm -rf .venv dist build *.egg-info .pytest_cache .ruff_cache .ty_cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    @echo "✓ Clean complete"

# === Testing ===

# Run tests with pytest
test *ARGS:
    uv run pytest tests/ {{ARGS}}

# Run tests with coverage
test-cov:
    uv run pytest tests/ --cov=src/nyctea --cov-report=xml --cov-report=term --cov-report=html

# Run tests on all Python versions (mimics CI)
test-all:
    @./scripts/test-all-versions.sh

# Run tests quickly (quiet mode)
test-quick:
    uv run pytest tests/ -q --tb=line

# === Code Quality ===

# Run all pre-commit hooks
pre-commit:
    uv run pre-commit run --all-files

# Run pre-commit on staged files only
pre-commit-staged:
    uv run pre-commit run

# Run linters (ruff + ty)
lint:
    uv run ruff check src/ tests/
    uv run ty check src/nyctea

# Run ruff formatter
format:
    uv run ruff format src/ tests/

# Fix linting issues automatically
fix:
    uv run ruff check --fix src/ tests/

# Run type checker on stable modules
typecheck:
    uv run ty check src/nyctea

# Run type checker on a specific path
typecheck-path PATH:
    uv run ty check {{PATH}}

# Run security vulnerability scan
secure:
    uv run uv-secure

# === GitHub Actions Simulation ===

# Simulate GitHub Actions CI locally
ci: ci-lint ci-test ci-typecheck
    @echo "✓ All CI checks passed!"

# Simulate CI: Lint job
ci-lint:
    @echo "=== Running CI: Lint ==="
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Simulate CI: Test job (all Python versions)
ci-test:
    @echo "=== Running CI: Test (all Python versions) ==="
    @./scripts/test-all-versions.sh

# Simulate CI: Type check job
ci-typecheck:
    @echo "=== Running CI: Type Check ==="
    uv run ty check src/nyctea

# Simulate CI: Build job
ci-build:
    @echo "=== Running CI: Build ==="
    @./scripts/ci-build.sh

# === Building & Publishing ===

# Build distribution packages
build:
    @echo "Building package..."
    uv build
    @echo "✓ Build complete. Check dist/ directory"

# Build and verify package
build-check: build
    @echo "Checking package..."
    uv run twine check dist/*
    @echo "✓ Package check passed"

# Install package locally for testing
install-local:
    uv pip install --editable .

# === Documentation ===

# Build documentation
docs-build:
    @echo "Building documentation..."
    uv run --group docs zensical build
    @echo "✓ Documentation built to public/"

# Serve documentation locally
docs-serve:
    @echo "Serving documentation at http://localhost:8000"
    uv run --group docs zensical serve

# === Utilities ===

# Update pre-commit hooks
update-hooks:
    uv run pre-commit autoupdate

# Update dependencies
update-deps:
    uv lock --upgrade

# Show project status
status:
    @echo "=== Python Versions ==="
    @uv python list | grep cpython | head -5
    @echo ""
    @echo "=== Installed Packages ==="
    @uv pip list | head -10
    @echo "... (showing first 10)"
    @echo ""
    @echo "=== Git Status ==="
    @git status --short

# Run all checks before committing
check: pre-commit test-quick typecheck
    @echo "✓ All checks passed! Ready to commit."

# Full validation (runs everything)
validate: clean setup ci build-check
    @echo "✓ Full validation complete!"
