"""Every local command that checks a distribution matches the one CI runs.

The justfile, the two scripts under `scripts/`, and the build workflow all check the
built wheel and sdist. When they drift, the local ones fail at the moment they matter
and CI stays green, so nobody notices until a release. `just build-check` called
`uv run twine check`, which cannot work because twine is not a project dependency, and
`scripts/release.sh` ran `uv run pip install twine` first, which cannot work either
because pip is not in a uv-managed environment. `uv pip install twine` would work but
does not survive a `uv sync`, since an undeclared package is removed again.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

TWINE_CHECK = "uv run --group release twine check"

TWINE_CALLERS = ("justfile", "scripts/ci-build.sh", "scripts/release.sh", ".github/workflows/build.yaml")


@pytest.mark.parametrize("relative_path", TWINE_CALLERS)
def test_twine_invocation_is_shared(relative_path):
    """Twine is declared in the `release` group, so every caller runs it the same way."""
    text = (ROOT / relative_path).read_text()
    twine_lines = [
        line.strip() for line in text.splitlines() if "twine check" in line and not line.lstrip().startswith("#")
    ]

    assert twine_lines, f"{relative_path} no longer checks the distribution at all"
    for line in twine_lines:
        assert line.startswith(TWINE_CHECK), f"{relative_path} runs {line!r}, expected {TWINE_CHECK!r}"


def test_nothing_installs_into_the_project_venv():
    """`uv run pip ...` fails outright, and a release must not mutate the venv it uses."""
    offenders = [
        f"{path}:{number}"
        for path in TWINE_CALLERS
        for number, line in enumerate((ROOT / path).read_text().splitlines(), start=1)
        if "uv run pip install" in line and not line.lstrip().startswith("#")
    ]

    assert offenders == [], f"install into the project environment: {offenders}"
