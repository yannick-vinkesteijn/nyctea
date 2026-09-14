"""Every local command that checks a distribution matches the one CI runs.

The justfile, the two scripts under `scripts/`, and the build workflow all check the
built wheel and sdist. When they drift, the local ones fail at the moment they matter
and CI stays green, so nobody notices until a release. `just build-check` called
`uv run twine check`, which cannot work because twine is not a project dependency, and
`scripts/release.sh` ran `uv run pip install twine` first, which cannot work either
because pip is not in a uv-managed environment. `uv pip install twine` would work but
does not survive a `uv sync`, since an undeclared package is removed again.

`--only-group` rather than `--group`: on a clean runner the latter also syncs the
default `dev` group, so checking a distribution installed 68 packages instead of 22 and
could fail over a test or docs dependency unrelated to the artifact.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

TWINE_CHECK = "uv run --only-group release twine check"
TWINE_TARGET = "dist/*"

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
        # Without a target the command checks nothing and still exits 0, so the prefix
        # alone would pass a caller that had quietly stopped inspecting the build.
        assert line.split()[-1] == TWINE_TARGET, f"{relative_path} runs {line!r}, expected it to end {TWINE_TARGET!r}"


def test_no_ad_hoc_twine_install():
    """Twine comes from the locked `release` group, never from an install in the script.

    `uv run --only-group release` does put twine in the environment; what must not
    happen is a caller installing it itself. `uv run pip install` fails outright, and
    `uv pip install` succeeds but does not survive the next `uv sync`, so both leave
    the check depending on whatever a machine happens to have.
    """
    offenders = [
        f"{path}:{number}"
        for path in TWINE_CALLERS
        for number, line in enumerate((ROOT / path).read_text().splitlines(), start=1)
        if "twine" in line
        and ("uv run pip install" in line or "uv pip install" in line)
        and not line.lstrip().startswith("#")
    ]

    assert offenders == [], f"ad hoc twine install, use the locked `release` group: {offenders}"


def test_setup_leaves_out_the_release_group():
    """The documented onboarding command does not install a release-only tool.

    `release` exists so that only a release pays for twine and its dependency chain.
    `just setup` syncs `--all-groups`, which would pull the group in anyway and make
    that separation pointless, so it excludes the group explicitly.
    """
    setup = [line.strip() for line in (ROOT / "justfile").read_text().splitlines() if "uv sync" in line]

    assert setup, "the setup recipe no longer syncs anything"
    for line in setup:
        assert "--no-group release" in line, f"`just setup` runs {line!r} and would install twine for everyone"
