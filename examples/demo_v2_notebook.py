import marimo

__generated_with = "0.18.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md("""
    # Nyctea v0.2.0 — Validation Pipeline Demo

    Nyctea is a Polars-based data validation library. This notebook walks
    through a realistic scenario: a hospital receives messy patient data
    from three different source systems. Column names differ, types are
    wrong, values are out of range, and whitespace is everywhere.

    We will define a schema once and let Nyctea clean it up.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 1. The problem: dirty data from three sources

    Source A uses `pid`, source B uses `AGE` instead of `age`, and
    source C dumps everything as strings with trailing spaces.
    Some values are clearly wrong: an age of 150, a temperature of 45,
    and a status that does not exist in the codebook.
    """)
    return


@app.cell
def _():
    import polars as pl

    dirty = pl.DataFrame(
        {
            "pid": ["  001", "002", "003 ", "004", "005", "006"],
            "AGE": ["34", "not_a_number", "150", "29", "-5", "67"],
            "temperature": ["36.6", "abc", "45.2", "37.1", "36.8", "38.0"],
            "status": [" Active ", "DISCHARGED", "unknown", "active", "  Deceased", None],
        }
    )
    dirty
    return (dirty,)


@app.cell
def _(mo):
    mo.md("""
    ## 2. Define a schema

    The schema describes what **clean** data looks like. Each column has:

    - **dtype** — the target Polars type
    - **synonyms** — alternative names to accept (handles source A vs B)
    - **parsers** — transformations applied before type casting (strip, lowercase)
    - **checks** — validations applied after casting (range, allowed values)
    - **nullable** — whether nulls are acceptable

    Coercion is enabled globally: columns will be cast to their target dtype.
    """)
    return


@app.cell
def _():
    from nyctea import SchemaModel

    schema = SchemaModel.from_dict(
        {
            "coerce": True,
            "on_failure": "null",
            "columns": {
                "patient_id": {
                    "dtype": "Utf8",
                    "synonyms": ["pid", "patient_no"],
                    "parsers": [{"name": "strip"}],
                    "nullable": False,
                    "on_failure": "raise",
                },
                "age": {
                    "dtype": "Int64",
                    "synonyms": ["Age", "AGE", "age_years"],
                    "parsers": [{"name": "strip"}],
                    "checks": [{"name": "between", "args": {"min": 0, "max": 120}}],
                    "nullable": True,
                },
                "temperature": {
                    "dtype": "Float64",
                    "parsers": [{"name": "strip"}],
                    "checks": [{"name": "between", "args": {"min": 35.0, "max": 42.0}}],
                    "nullable": True,
                },
                "status": {
                    "dtype": "Utf8",
                    "parsers": [{"name": "strip"}, {"name": "lower"}],
                    "checks": [
                        {
                            "name": "in_set",
                            "args": {"values": ["active", "discharged", "deceased"]},
                        }
                    ],
                    "nullable": True,
                },
            },
        }
    )
    schema
    return (schema,)


@app.cell
def _(mo):
    mo.md("""
    ## 3. The pipeline

    Under the hood Nyctea builds a lazy pipeline of phases.
    Everything stays as a Polars `LazyFrame` until the very end.

    ```
    ColumnResolutionPhase   pid -> patient_id, AGE -> age
          |
    ColumnParsingPhase      strip whitespace, lowercase
          |
    CoercionPhase           cast str -> Int64, str -> Float64
          |
    ColumnCheckPhase        between, in_set (boolean masks, no collect)
          |
    [collect]               single materialisation at the API boundary
    ```

    Zero intermediate collects. For a schema with 10 columns and 5
    checks each, the old engine ran ~50 collects. This pipeline runs **one**.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. Lenient mode — `on_failure: "null"`

    The schema sets `on_failure: "null"` as the default. When a cast fails
    (e.g. `"not_a_number"` to Int64), the value becomes `null` instead of
    raising. The pipeline continues and reports every issue it finds.

    `patient_id` overrides to `on_failure: "raise"` because it must be clean.
    """)
    return


@app.cell
def _(dirty, schema):
    from nyctea import Registry, register_builtins

    registry = Registry()
    register_builtins(registry)

    result_lenient = schema.validate(
        dirty,
        registry,
        lazy=False,
    )
    return registry, result_lenient


@app.cell
def _(mo):
    mo.md("""
    ### Cleaned output
    """)
    return


@app.cell
def _(result_lenient):
    result_lenient.data
    return


@app.cell
def _(mo):
    mo.md("""
    **What happened:**

    | Row | Issue | Resolution |
    |-----|-------|------------|
    | 1 | `pid` had leading spaces | Stripped to `001` |
    | 2 | `"not_a_number"` in age | Cast failed -> `null` |
    | 2 | `"abc"` in temperature | Cast failed -> `null` |
    | 3 | age = 150 | Cast succeeded, but **check failed** (> 120) |
    | 3 | temperature = 45.2 | Cast succeeded, but **check failed** (> 42.0) |
    | 3 | status = `"unknown"` | Not in allowed set |
    | 5 | age = -5 | **Check failed** (< 0) |
    | all | `"DISCHARGED"`, `" Active "` | Lowercased and stripped |
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ### Error summary
    """)
    return


@app.cell
def _(result_lenient):
    result_lenient.errors
    return


@app.cell
def _(mo):
    mo.md("""
    ### Validation report
    """)
    return


@app.cell
def _(mo, result_lenient):
    mo.md(f"""
    ```\n{result_lenient.report.summary()}\n```
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Strict mode

    In production you often want to fail fast. With `on_failure: "raise"`,
    the first column with a coercion failure raises a `PipelineError`.
    """)
    return


@app.cell
def _(dirty, mo, registry):
    from nyctea import SchemaModel as _SM
    from nyctea.exceptions import PipelineError

    strict_schema = _SM.from_dict(
        {
            "coerce": True,
            "on_failure": "raise",
            "columns": {
                "patient_id": {"dtype": "Utf8", "synonyms": ["pid"], "parsers": [{"name": "strip"}], "nullable": False},
                "age": {"dtype": "Int64", "synonyms": ["Age", "AGE"], "parsers": [{"name": "strip"}], "nullable": True},
                "temperature": {"dtype": "Float64", "parsers": [{"name": "strip"}], "nullable": True},
                "status": {"dtype": "Utf8", "parsers": [{"name": "strip"}, {"name": "lower"}], "nullable": True},
            },
        }
    )

    try:
        strict_schema.validate(dirty, registry)
        _strict_output = mo.md("All casts succeeded (unexpected).")
    except PipelineError as e:
        _strict_output = mo.callout(
            mo.md(f"**`PipelineError`**: {e}"),
            kind="danger",
        )
    _strict_output
    return


@app.cell
def _(mo):
    mo.md("""
    ## 6. Schema from YAML

    Schemas can also be defined in YAML for easy version control.

    ```yaml
    coerce: true
    on_failure: "null"
    columns:
      patient_id:
        dtype: Utf8
        synonyms: [pid, patient_no]
        parsers:
          - name: strip
        nullable: false
        on_failure: raise
      age:
        dtype: Int64
        synonyms: [Age, AGE]
        parsers:
          - name: strip
        checks:
          - name: between
            args: {min: 0, max: 120}
        nullable: true
    ```
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 7. Lazy output

    By default Nyctea returns a `LazyFrame`. This lets you chain
    further Polars operations before materialising, or write directly
    to Parquet without loading the full dataset into memory.
    """)
    return


@app.cell
def _(dirty, registry, schema):
    result_lazy = schema.validate(
        dirty,
        registry,
        lazy=True,
    )
    # Still a LazyFrame — no data materialised yet
    result_lazy.data.explain()
    return


@app.cell
def _(mo):
    mo.md("""
    ## What is next

    Steps 3-6 on the v0.2.0 roadmap will add:

    - **ErrorReportingPhase** — row-level and cell-level error detail
    - **Report generation** — accurate `rows_valid` count using check masks
    - **NullificationPhase** — set failing values to `null` for lenient columns
    - **Frame-level plugins** — whole-frame parsers and checks (e.g. deduplication)
    """)
    return


@app.cell
def _():
    import marimo as mo
    return (mo,)


if __name__ == "__main__":
    app.run()
