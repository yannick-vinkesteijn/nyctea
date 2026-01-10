"""Marimo notebook to explore and validate the Titanic example data."""

import marimo

__generated_with = "0.18.4"
app = marimo.App()


@app.cell
def _():
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    for path in (project_root / "src", project_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    from nyctea.engine import ErrorReportConfig, validate
    from nyctea.ingest import read_csv
    from nyctea.schema.model import SchemaModel
    return ErrorReportConfig, SchemaModel, project_root, read_csv, validate


@app.cell
def _(SchemaModel, project_root):
    from examples.titanic_example.functions import registry

    schema_path = project_root / "examples/titanic_example/schema.yaml"
    data_path = project_root / "examples/titanic_example/titanic_sample.csv"
    schema = SchemaModel.from_yaml_file(schema_path)
    return data_path, registry, schema


@app.cell
def _(data_path, read_csv, schema):
    lf = read_csv(data_path, schema, lazy=True)
    lf
    return (lf,)


@app.cell
def _(ErrorReportConfig, lf, registry, schema, validate):
    # Use summary mode for quick overview
    error_config = ErrorReportConfig(mode="summary")
    result = validate(
        lf,
        schema,
        registry,
        lazy=True,
        coerce_strategy="null_on_failure",
        error_report=error_config,
    )
    errors = result.errors
    data_out = result.data
    return data_out, errors


@app.cell
def _(errors):
    errors
    return


@app.cell
def _(data_out):
    if hasattr(data_out, "explain"):
        data_out.explain(engine="default")  # or engine="streaming"

    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
