#!/usr/bin/env bash
# Release script for Nyctea
# Usage: ./scripts/release.sh [version]
# Example: ./scripts/release.sh 0.2.0

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    exit 1
}

info() {
    echo -e "${GREEN}INFO: $1${NC}"
}

warn() {
    echo -e "${YELLOW}WARNING: $1${NC}"
}

# Check if version is provided
if [ $# -eq 0 ]; then
    error "Version number required. Usage: ./scripts/release.sh 0.2.0"
fi

VERSION="$1"

# Validate version format (semantic versioning)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    error "Invalid version format. Use semantic versioning: X.Y.Z (e.g., 0.2.0)"
fi

# Check if on clean branch
if [ -n "$(git status --porcelain)" ]; then
    error "Working directory is not clean. Commit or stash changes first."
fi

# Check if on main branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
    warn "You're on branch '$CURRENT_BRANCH', not 'main'. Continue? (y/n)"
    read -r response
    if [ "$response" != "y" ]; then
        exit 0
    fi
fi

info "Starting release process for version $VERSION"

# Step 1: Update version in pyproject.toml
info "Updating version in pyproject.toml..."
sed -i.bak "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
rm pyproject.toml.bak

# Step 2: Run tests
info "Running tests..."
if ! uv run pytest tests/ -v; then
    error "Tests failed. Fix tests before releasing."
fi

# Step 3: Build package
info "Building package..."
rm -rf dist/
uv build

# Step 4: Check package
info "Checking package with twine..."
uv run pip install twine
uv run twine check dist/*

# Step 5: Show files
info "Package built successfully:"
ls -lh dist/

# Step 6: Ask for confirmation
echo ""
warn "Ready to publish version $VERSION. Next steps:"
echo "  1. Publish to TestPyPI (recommended)"
echo "  2. Publish to PyPI"
echo "  3. Commit version bump"
echo "  4. Create git tag"
echo ""
echo "Publish to TestPyPI first? (y/n)"
read -r test_pypi

if [ "$test_pypi" = "y" ]; then
    info "Publishing to TestPyPI..."
    uv publish --index https://test.pypi.org/legacy/ dist/*
    info "Published to TestPyPI. Test it with:"
    echo "  uv pip install --index-url https://test.pypi.org/simple/ nyctea==$VERSION"
    echo ""
    echo "Continue with PyPI publish? (y/n)"
    read -r continue_pypi
    if [ "$continue_pypi" != "y" ]; then
        info "Stopping before PyPI publish. Version updated in pyproject.toml."
        exit 0
    fi
fi

# Step 7: Publish to PyPI
echo ""
warn "Publish to PyPI? This cannot be undone! (y/n)"
read -r publish_pypi

if [ "$publish_pypi" = "y" ]; then
    info "Publishing to PyPI..."
    uv publish dist/*
    info "Published to PyPI successfully!"

    # Step 8: Commit version bump
    info "Committing version bump..."
    git add pyproject.toml
    git commit -m "Bump version to $VERSION"

    # Step 9: Create and push tag
    info "Creating git tag v$VERSION..."
    git tag "v$VERSION"

    echo ""
    info "Release $VERSION complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Push changes: git push origin main"
    echo "  2. Push tag: git push origin v$VERSION"
    echo "  3. Create GitHub release: https://github.com/yannick-vinkesteijn/nyctea/releases/new?tag=v$VERSION"
else
    info "Skipped PyPI publish. Version updated in pyproject.toml."
fi
