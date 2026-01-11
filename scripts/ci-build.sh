#!/bin/bash
# Simulate GitHub Actions Build workflow locally

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Simulating GitHub Actions: Build ===${NC}"
echo ""

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist/
echo ""

# Build job
echo -e "${BLUE}Job: build${NC}"
echo "========================================="

echo "Building package..."
uv build

echo ""
echo "Checking package with twine..."
uv run twine check dist/*

echo ""
echo -e "${GREEN}✓ Build job passed${NC}"
echo ""

# Install-test job
echo -e "${BLUE}Job: install-test${NC}"
echo "========================================="

# Save current venv
ORIG_VENV=".venv"
if [ -d "$ORIG_VENV" ]; then
    mv "$ORIG_VENV" "${ORIG_VENV}.backup-build"
fi

# Create fresh venv
echo "Creating fresh virtual environment..."
uv venv .venv
source .venv/bin/activate

echo ""
echo "Installing built wheel..."
uv pip install dist/*.whl

echo ""
echo "Testing import..."
python -c "from nyctea import SchemaModel, MasterRegistry, register_builtins; print('✅ Import successful')"

deactivate

# Restore original venv
rm -rf .venv
if [ -d "${ORIG_VENV}.backup-build" ]; then
    mv "${ORIG_VENV}.backup-build" "$ORIG_VENV"
fi

echo ""
echo -e "${GREEN}✓ Install-test job passed${NC}"
echo ""

echo "========================================="
echo -e "${GREEN}✓ All build jobs passed!${NC}"
echo "========================================="
