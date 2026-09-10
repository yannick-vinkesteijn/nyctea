"""Guard on how test functions are named.

A test name is read far more often than it is written, in a failure line that has
no room for a sentence. The cap keeps names to a label rather than a restatement of
the assertion, and the docstring carries the detail.

The cap applies with no exemptions. `tests/test_design_principles.py` is the model.
"""

import ast
import pathlib

TESTS = pathlib.Path(__file__).resolve().parent

MAX_WORDS = 6
"""Underscore-separated words after the `test_` prefix."""


def _test_names() -> set[str]:
    """Every `test_*` function defined under `tests/`."""
    names: set[str] = set()
    for path in sorted({*TESTS.rglob("test_*.py"), *TESTS.rglob("*_test.py")}):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                names.add(node.name)
    return names


def _word_count(name: str) -> int:
    return len(name.removeprefix("test_").split("_"))


def test_test_names_fit_the_word_cap():
    over_cap = sorted(name for name in _test_names() if _word_count(name) > MAX_WORDS)
    assert not over_cap, (
        f"Test names may use at most {MAX_WORDS} words after `test_`. "
        f"Shorten these or move the detail into the docstring: {over_cap}"
    )
