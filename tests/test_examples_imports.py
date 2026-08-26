"""Guard that everything under examples/ still imports a real part of the public API.

examples/ is excluded from ruff and sits outside pre-commit's `ty check src/nyctea`,
so nothing else notices when a refactor deletes or renames something an example uses.
That is not hypothetical: removing `nyctea.engine.results` left two dead imports in
`examples/demo_v2_notebook.py`.

This parses rather than imports, so it needs no optional dependency (marimo) and runs
no example code.
"""

import ast
import importlib
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _nyctea_imports(path: Path) -> list[tuple[str, str | None]]:
    """Collect (module, attribute) pairs for every nyctea import in one file.

    Args:
        path: Python file to parse.

    Returns:
        Pairs where attribute is None for a plain `import nyctea.x` and the imported
        name for a `from nyctea.x import name`.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "nyctea":
            found.extend((node.module, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            found.extend((alias.name, None) for alias in node.names if alias.name.split(".")[0] == "nyctea")
    return found


def _example_files() -> list[Path]:
    return sorted(p for p in EXAMPLES.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.parametrize("path", _example_files(), ids=lambda p: str(p.relative_to(EXAMPLES)))
def test_example_nyctea_imports_resolve(path: Path) -> None:
    """Every nyctea module and name an example imports must still exist."""
    for module_name, attr in _nyctea_imports(path):
        module = importlib.import_module(module_name)
        if attr is not None:
            assert hasattr(module, attr), (
                f"{path.relative_to(EXAMPLES)} imports '{attr}' from '{module_name}', which no longer provides it"
            )
