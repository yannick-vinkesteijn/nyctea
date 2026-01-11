#!/bin/bash
# Run full CI simulation (all workflows)

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║  Full CI Simulation - All Workflows   ║${NC}"
echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo ""

FAILED_JOBS=()

# Lint job
echo -e "${BLUE}▶ Running Lint workflow...${NC}"
echo ""
if "$SCRIPT_DIR/ci-lint.sh"; then
    echo -e "${GREEN}✓ Lint passed${NC}"
else
    echo -e "${RED}✗ Lint failed${NC}"
    FAILED_JOBS+=("Lint")
fi
echo ""

# Test job (all Python versions)
echo -e "${BLUE}▶ Running Test workflow (all Python versions)...${NC}"
echo ""
if "$SCRIPT_DIR/test-all-versions.sh"; then
    echo -e "${GREEN}✓ Tests passed${NC}"
else
    echo -e "${RED}✗ Tests failed${NC}"
    FAILED_JOBS+=("Test")
fi
echo ""

# Type check job
echo -e "${BLUE}▶ Running Type Check...${NC}"
echo ""
if uv run mypy src/nyctea --ignore-missing-imports; then
    echo -e "${GREEN}✓ Type check passed${NC}"
else
    echo -e "${YELLOW}⚠ Type check has warnings (non-blocking)${NC}"
fi
echo ""

# Build job
echo -e "${BLUE}▶ Running Build workflow...${NC}"
echo ""
if "$SCRIPT_DIR/ci-build.sh"; then
    echo -e "${GREEN}✓ Build passed${NC}"
else
    echo -e "${RED}✗ Build failed${NC}"
    FAILED_JOBS+=("Build")
fi
echo ""

# Summary
echo ""
echo -e "${YELLOW}═══════════════════════════════════════${NC}"
echo -e "${YELLOW}  CI Summary${NC}"
echo -e "${YELLOW}═══════════════════════════════════════${NC}"

if [ ${#FAILED_JOBS[@]} -eq 0 ]; then
    echo -e "${GREEN}✓ All workflows passed!${NC}"
    echo ""
    echo "Your code is ready to push! 🚀"
    exit 0
else
    echo -e "${RED}✗ Failed workflows:${NC}"
    for job in "${FAILED_JOBS[@]}"; do
        echo -e "${RED}  - $job${NC}"
    done
    echo ""
    echo "Please fix the issues before pushing."
    exit 1
fi
