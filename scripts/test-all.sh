#!/usr/bin/env bash
set -e

VERSIONS=("3.11" "3.12" "3.13" "3.14")
FAILED=()

for version in "${VERSIONS[@]}"; do
    echo "--- Python $version ---"
    if uv run --python "$version" python examples/titanic_example/run_validation.py; then
        echo "PASS $version"
    else
        echo "FAIL $version"
        FAILED+=("$version")
    fi
done

if [ ${#FAILED[@]} -ne 0 ]; then
    echo "Failed on: ${FAILED[*]}"
    exit 1
fi

echo "All versions passed."
