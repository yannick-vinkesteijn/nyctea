"""Guards on the design principles that can be checked mechanically.

`.agents/design/202609022241_schema-object-and-pipeline-structure.md` ends with a
review checklist. Most of it is judgement, but several items are structural facts
about the source, and a rule in prose drifts while a rule here fails loudly.

`tests/test_import_structure.py` covers the layering items. This file covers the
rest. Rules ruff already enforces are not repeated: the lint config selects `ALL`,
so `print`, `typing.List` and `from __future__ import annotations` are its job.
"""

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "nyctea"


def _modules() -> list[tuple[pathlib.Path, ast.Module]]:
    """Parse every module under `src/nyctea`, newest state on disk."""
    return [(path, ast.parse(path.read_text())) for path in sorted(SRC.rglob("*.py"))]


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(SRC))


# Classes whose whole job is to accumulate across calls, so writing to `self` is
# their contract rather than hidden working state. The design document names
# `PipelineContext` as the deliberate exception; these are the same shape.
STATEFUL_BY_DESIGN = {
    # An observer that collects timings across pipeline callbacks. It has nowhere
    # else to put them, since the observer protocol returns nothing.
    ("MetricsCollector", "on_pipeline_start"),
    ("MetricsCollector", "on_pipeline_complete"),
    ("MetricsCollector", "on_pipeline_error"),
    # A re-entrancy guard, not a value passed from one method to another.
    ("ValidationPipeline", "execute"),
}


def test_no_method_stores_working_state_on_self():
    """Methods pass data by argument and return value.

    The rule bans *intermediate* state, meaning a value one method writes and
    another reads, which makes call order matter. Constructor assignments are
    fine, and so are the accumulators named above.
    """
    offenders = []
    for path, tree in _modules():
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name != "__init__"]:
                if (cls.name, fn.name) in STATEFUL_BY_DESIGN:
                    continue
                offenders.extend(
                    f"{_rel(path)}:{node.lineno} {cls.name}.{fn.name} sets self.{target.attr}"
                    for node in ast.walk(fn)
                    if isinstance(node, ast.Assign)
                    for target in node.targets
                    if isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                )

    assert offenders == [], "methods must not stash working values on self:\n" + "\n".join(offenders)


def test_every_cached_property_on_the_schema_is_a_declared_derived_view():
    """A view missing from `_DERIVED_VIEWS` is lazy and can be rebuilt mid-run.

    The schema is frozen so that every derived view is computed once, at
    construction. `_DERIVED_VIEWS` is what drives that eager build and the rebuild
    after unpickling, so a `cached_property` absent from it silently reverts to
    first-use computation.
    """
    tree = ast.parse((SRC / "schema" / "model.py").read_text())

    declared: set[str] = set()
    for node in ast.walk(tree):
        is_views = isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_DERIVED_VIEWS"
        is_plain = isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_DERIVED_VIEWS" for t in node.targets)
        if (is_views or is_plain) and isinstance(node.value, ast.Tuple):
            declared = {e.value for e in node.value.elts if isinstance(e, ast.Constant)}

    assert declared, "could not find _DERIVED_VIEWS in schema/model.py"

    schema_model = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SchemaModel")
    cached = {
        fn.name
        for fn in schema_model.body
        if isinstance(fn, ast.FunctionDef) and any(getattr(d, "id", "") == "cached_property" for d in fn.decorator_list)
    }

    assert cached - declared == set(), (
        f"cached_property missing from _DERIVED_VIEWS, so built lazily: {sorted(cached - declared)}"
    )
    assert declared - cached == set(), (
        f"_DERIVED_VIEWS names something that is not a cached_property: {sorted(declared - cached)}"
    )


# Callers that still derive something by walking the authoring shape. Each one
# should become a named view on `SchemaModel`. The list only shrinks.
KNOWN_SCHEMA_COLUMN_LOOPS = {
    # Dead code. `SchemaModel.resolve_columns` supersedes it; phase 1.4 deletes it.
    "engine/utils.py",
    # Builds a name-to-dtype map including synonyms. Wants a `dtype_by_accepted_name`
    # view rather than a loop over the authoring shape.
    "ingest/readers.py",
}


def test_no_new_caller_derives_by_looping_the_authoring_shape():
    """`schema.columns` is the authoring shape. Consumers read named views.

    Re-deriving a predicate from `columns.items()` is the duplication #86 exists to
    remove: every consumer that does it reimplements inheritance resolution and can
    disagree with the others.
    """
    offenders = set()
    for path, tree in _modules():
        if _rel(path) == "schema/model.py":
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            call = node.iter
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr in {"items", "values"}
                and isinstance(call.func.value, ast.Attribute)
                and call.func.value.attr == "columns"
                and getattr(call.func.value.value, "id", "") == "schema"
            ):
                offenders.add(_rel(path))

    assert offenders <= KNOWN_SCHEMA_COLUMN_LOOPS, (
        "new caller deriving from schema.columns instead of a named view: "
        f"{sorted(offenders - KNOWN_SCHEMA_COLUMN_LOOPS)}"
    )


def test_no_new_row_data_is_pulled_into_python_lists():
    """Data-scale values stay in Polars.

    Measured at a consistent 10x memory for the round trip out of Arrow, and
    unbounded when no error limit is set. The three below are the error builders'
    `implode()` to `.item().to_list()` round trip, tracked in #84. The count only
    goes down.
    """
    found = [
        f"{_rel(path)}:{i}"
        for path, _ in _modules()
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if ".to_list()" in line or ".to_dicts()" in line or ".rows()" in line
    ]

    assert len(found) <= 3, "new Arrow-to-Python round trip, keep it in Polars (see #84):\n" + "\n".join(found)
