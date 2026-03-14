#!/bin/bash
# Test across all Python versions (mimics GitHub Actions CI)

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

VERSIONS=("3.10" "3.11" "3.12" "3.13" "3.14")

echo -e "${BLUE}=== Testing Python Versions ===${NC}"
echo ""

# Save original venv
ORIG_VENV=".venv"
if [ -d "$ORIG_VENV" ]; then
    mv "$ORIG_VENV" "${ORIG_VENV}.backup"
fi

FAILED=0
PASSED=0

for version in "${VERSIONS[@]}"; do
    echo -e "${BLUE}Testing Python $version${NC}"
    echo "========================================="

    # Clean venv
    rm -rf .venv

    # Install Python version
    uv python install "$version" > /dev/null 2>&1 || true

    # Install dependencies
    if ! uv sync --python "$version" --group test --quiet 2>&1; then
        echo -e "${RED}✗ Failed to install dependencies for Python $version${NC}"
        FAILED=$((FAILED + 1))
        continue
    fi

    # Run tests
    if uv run pytest tests/ -q --tb=line 2>&1 | tail -3; then
        echo -e "${GREEN}✓ Python $version passed${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗ Python $version failed${NC}"
        FAILED=$((FAILED + 1))
    fi

    echo ""
done

# Restore original venv
rm -rf .venv
if [ -d "${ORIG_VENV}.backup" ]; then
    mv "${ORIG_VENV}.backup" "$ORIG_VENV"
else
    # Recreate with default Python if no backup
    uv sync --group test --quiet
fi

# Summary
echo "========================================="
echo -e "${BLUE}Test Summary${NC}"
echo "========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All Python versions passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some Python versions failed${NC}"
    exit 1
fi
