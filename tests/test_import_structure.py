"""Guards on the package's import structure.

The intended shape is a tree: an orchestrator on top, phases below it, and shared
objects at the leaves. Layers import downward only. The one exception is the API
boundary, where `SchemaModel.validate()` reaches into the engine through a
deferred import so that users get one obvious entry point.

See `.agents/design/202609022241_schema-object-and-pipeline-structure.md` and #86.
"""

import ast
import collections
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "nyctea"


def _import_graph(*, module_scope_only: bool = False) -> dict[str, set[str]]:
    """Map each nyctea module to the nyctea modules it imports.

    ``module_scope_only`` restricts the graph to imports Python actually resolves
    at import time. Those are the ones that can fail. Imports inside
    ``TYPE_CHECKING`` blocks and function bodies never do, so they are counted
    only when looking for the softer signal of a dependency pointing upward.
    """
    graph: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        module = ".".join(path.relative_to(SRC.parent).with_suffix("").parts)
        module = module.removesuffix(".__init__")
        deps: set[str] = set()

        def collect(node: ast.AST, at_module_scope: bool, deps: set[str] = deps) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.If) and "TYPE_CHECKING" in ast.dump(child.test):
                    if not module_scope_only:
                        collect(child, at_module_scope)
                    continue
                if isinstance(child, ast.ImportFrom):
                    if (
                        child.module
                        and child.module.startswith("nyctea")
                        and (at_module_scope or not module_scope_only)
                    ):
                        deps.add(child.module)
                elif isinstance(child, ast.Import):
                    if at_module_scope or not module_scope_only:
                        deps.update(a.name for a in child.names if a.name.startswith("nyctea"))
                else:
                    nested = at_module_scope and isinstance(child, ast.ClassDef)
                    collect(
                        child,
                        nested
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        else at_module_scope,
                    )

        collect(ast.parse(path.read_text()), True)
        graph[module] = deps - {module}

    known = set(graph)
    return {module: deps & known for module, deps in graph.items()}


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return every import cycle, each as the list of modules forming it."""
    white, grey, black = 0, 1, 2
    colour: dict[str, int] = collections.defaultdict(int)
    cycles: list[list[str]] = []

    def visit(module: str, stack: list[str]) -> None:
        colour[module] = grey
        stack.append(module)
        for dep in sorted(graph.get(module, ())):
            if colour[dep] == grey:
                cycles.append([*stack[stack.index(dep) :], dep])
            elif colour[dep] == white:
                visit(dep, stack)
        stack.pop()
        colour[module] = black

    for module in sorted(graph):
        if colour[module] == white:
            visit(module, [])
    return cycles


def test_the_package_root_is_the_only_composition_point():
    """Nothing may import `nyctea` itself.

    The root is allowed to import everything, which is what lets a convenience
    entry point live there without creating a cycle. That only holds while
    nothing imports back into it.
    """
    graph = _import_graph()
    importers = [module for module, deps in graph.items() if "nyctea" in deps and module != "nyctea"]

    assert importers == [], f"these import the package root, which would create a cycle: {importers}"


def test_every_import_cycle_traces_to_the_schema_reaching_into_the_engine():
    """Ratchet on the known cycles, all of which have one cause.

    `SchemaModel.validate()` and `create_validator()` construct engine objects, so
    `nyctea.schema.model` imports `nyctea.engine.*` under `TYPE_CHECKING` and in
    two function bodies. That single upward edge closes every cycle the softer
    graph reports. None of them break at runtime, see
    `test_no_module_scope_import_cycles`.

    This assertion fails on any *new* cycle introduced by a different cause,
    which would be a genuine structural regression.
    """
    cycles = _find_cycles(_import_graph())
    unrelated = [cycle for cycle in cycles if "nyctea.schema.model" not in cycle]

    assert unrelated == [], "new import cycle not caused by the known schema-to-engine dependency:\n" + "\n".join(
        " -> ".join(cycle) for cycle in unrelated
    )


def test_the_schema_package_does_not_import_the_engine_at_module_scope():
    """The one-way rule, enforced with no exemptions.

    `nyctea.schema` describes what a valid schema is. `nyctea.engine` runs
    validation against data. The dependency points one way, and at module scope
    it points that way everywhere, including in `nyctea.schema.model`. The
    sanctioned exception for `SchemaModel.validate()` is a deferred import, which
    Python never resolves at import time, so it does not appear in this graph.
    """
    graph = _import_graph(module_scope_only=True)
    offenders = {
        module: sorted(dep for dep in deps if dep.startswith("nyctea.engine"))
        for module, deps in graph.items()
        if module.startswith("nyctea.schema") and any(dep.startswith("nyctea.engine") for dep in deps)
    }

    assert offenders == {}, f"nyctea.schema must not import nyctea.engine: {offenders}"


def test_no_module_scope_import_cycles():
    """The rule that actually matters: no cycle Python resolves at import time.

    This already holds and must keep holding. The cycles the softer graph reports
    are all artefacts of ``TYPE_CHECKING`` blocks and function-body imports, none
    of which Python resolves during import, so none of which can raise
    ImportError.
    """
    cycles = _find_cycles(_import_graph(module_scope_only=True))

    assert cycles == [], "module-scope import cycle:\n" + "\n".join(" -> ".join(c) for c in cycles)


def test_the_api_boundary_is_the_only_upward_dependency():
    """Discount the one sanctioned exception, and nothing else points upward.

    `SchemaModel.validate()` and `create_validator()` construct engine objects,
    so `nyctea.schema.model` names `nyctea.engine` in a `TYPE_CHECKING` block and
    two function bodies. That is deliberate and stays: it is what makes
    `schema.validate(df, registry)` the first thing a user writes.

    Removing those edges is therefore the honest measure of the rest of the
    package. What remains must be acyclic, so any *new* upward dependency
    introduced anywhere else fails here rather than hiding among the cycles the
    boundary already accounts for.
    """
    graph = _import_graph()
    graph["nyctea.schema.model"] = {dep for dep in graph["nyctea.schema.model"] if not dep.startswith("nyctea.engine")}

    cycles = _find_cycles(graph)

    assert cycles == [], "upward dependency outside the sanctioned API boundary:\n" + "\n".join(
        " -> ".join(c) for c in cycles
    )


def test_the_only_type_checking_block_is_the_api_boundary():
    """A new `TYPE_CHECKING` block is a question, and this is where it gets asked.

    The design document treats a deferred or `TYPE_CHECKING` import as a signal
    that a dependency points the wrong way. Exactly one is sanctioned:
    `SchemaModel.validate()` reaching into the engine. Any other module growing one
    fails here, so the question gets asked deliberately rather than accreting.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        module = ".".join(path.relative_to(SRC.parent).with_suffix("").parts).removesuffix(".__init__")
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.If) and "TYPE_CHECKING" in ast.dump(node.test)):
                continue
            imported = [
                child.module
                for child in ast.walk(node)
                if isinstance(child, ast.ImportFrom) and child.module and child.module.startswith("nyctea")
            ]
            if imported and module != "nyctea.schema.model":
                offenders.append(f"{module}: {sorted(imported)}")

    assert offenders == [], (
        "new TYPE_CHECKING block importing nyctea. Ask whether the dependency points the wrong way:\n"
        + "\n".join(offenders)
    )
