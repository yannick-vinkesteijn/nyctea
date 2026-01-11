#!/bin/bash
# Simulate GitHub Actions Lint workflow locally

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Simulating GitHub Actions: Lint ===${NC}"
echo ""

echo "Running pyupgrade..."
find src tests -name "*.py" -type f -exec uv run pyupgrade --py310-plus --keep-runtime-typing {} +

echo ""
echo "Running Ruff linter..."
uv run ruff check src/ tests/

echo ""
echo "Running Ruff formatter check..."
uv run ruff format --check src/ tests/

echo ""
echo -e "${GREEN}✓ Lint job passed${NC}"
