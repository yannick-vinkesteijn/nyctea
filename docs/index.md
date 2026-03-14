---
icon: lucide/home
---

<div class="hero" markdown>
<div align="center" markdown>

![Nyctea](assets/logo-nyctea.png){ width="110" }

# Nyctea

**Polars-native data validation with a composable plugin pipeline.**

[Get started :octicons-arrow-right-24:](guides/quickstart.md){ .md-button .md-button--primary }
[View on GitHub :octicons-mark-github-16:](https://github.com/yourusername/nyctea){ .md-button }

</div>
</div>

---

=== ":material-package: uv"

    ```bash
    uv add nyctea
    ```

=== ":material-language-python: pip"

    ```bash
    pip install nyctea
    ```

---

## Features

<div class="grid cards" markdown>

-   :material-transit-connection-variant:{ .lg .middle } **Composable pipeline**

    ---

    Add, remove, or reorder validation phases. Inject custom logic anywhere without forking the library.

-   :material-puzzle-outline:{ .lg .middle } **Plugin registry**

    ---

    Register parsers and checks by name. Share a `Registry` across many schemas.

-   :material-lightning-bolt-outline:{ .lg .middle } **Lazy by default**

    ---

    All phases run on `LazyFrame`. Designed for datasets larger than RAM.

-   :material-file-code-outline:{ .lg .middle } **Schema as code or YAML**

    ---

    Define schemas in Python dicts, YAML, or JSON. Load from file or build programmatically.

-   :material-filter-outline:{ .lg .middle } **Parse then validate**

    ---

    Transform columns before checking. The output frame is already clean and typed.

-   :material-alert-circle-outline:{ .lg .middle } **Structured errors**

    ---

    Three reporting modes: summary counts, row indices, or cell values with `ErrorReportConfig`.

</div>

---

## Quick example

```python
from nyctea import SchemaModel, Registry, register_builtins
import polars as pl

schema = SchemaModel.from_dict({
    "columns": {
        "age":  {
            "dtype": "Int64",
            "nullable": False,
            "checks": [{"name": "min_value", "args": {"min": 0}}],
        },
        "name": {
            "dtype": "Utf8",
            "nullable": False,
            "parsers": [{"name": "strip"}, {"name": "lower"}],
        },
    }
})

registry = Registry()
register_builtins(registry)

df = pl.read_csv("data.csv")
result = schema.validate(df, registry)

print(result.report.summary())  # (1)!
result.errors                   # (2)!
```

1. Human-readable summary: rows processed, rows valid, per-column stats.
2. Structured `DataFrame` with column, check, and failure count per row.

---

## Browse the docs

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **User Guides**

    ---

    Get up and running. Learn schemas, parsers, checks, and the registry.

    [:octicons-arrow-right-24: Guides](guides/index.md)

-   :material-code-braces:{ .lg .middle } **API Reference**

    ---

    Full reference for `SchemaModel`, `Registry`, `ValidationResult`, and more.

    [:octicons-arrow-right-24: API](api/index.md)

-   :material-source-branch:{ .lg .middle } **Development**

    ---

    Architecture decisions, roadmap, and breaking change notes.

    [:octicons-arrow-right-24: Development](development/index.md)

-   :material-map-outline:{ .lg .middle } **Roadmap**

    ---

    What's planned for v0.2.0: pipeline phases, test coverage, and the path to main.

    [:octicons-arrow-right-24: Roadmap](development/roadmap.md)

</div>

---

## Why Nyctea?

Verified against Pandera 0.29.0 · Patito 0.8.6 · Dataframely 2.7.0 · Great Expectations 1.15.0.

|  | Nyctea | Pandera 0.29 | Patito 0.8.6 | Dataframely 2.7 |
|--|:------:|:-----------:|:-----------:|:--------------:|
| Polars-native | :material-check: | Partial (multi-backend) | :material-check: | :material-check: (Polars-only) |
| LazyFrame accepted | :material-check: | Partial¹ | Partial | :material-check: (`eager=False`) |
| True out-of-core / streaming | :material-check: | :material-close: | :material-close: | :material-close: (deferred²) |
| Plugin registry (Polars) | :material-check: | :material-close: (pandas only) | :material-close: | :material-close: |
| Composable pipeline phases | :material-check: | :material-close: | :material-close: | :material-close: |
| Parsers on Polars backend | :material-check: | :material-close: (pandas only) | :material-close: | :material-close: |

!!! note "Footnotes"
    ¹ Pandera `LazyFrame` requires `PANDERA_VALIDATION_DEPTH=SCHEMA_AND_DATA` for full data validation, which forces `collect()`. "Lazy validation" in Pandera means deferred error collection, not lazy execution.

    ² Dataframely `eager=False` defers validation to `collect()` time. Data must still fit in memory.

    Great Expectations 1.15 has no Polars support. The community request was closed as "not planned" in August 2024.

[Full comparison and citations :octicons-arrow-right-24:](development/adr-validation-api.md){ .md-button }
