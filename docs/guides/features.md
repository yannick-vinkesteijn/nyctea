---
icon: lucide/sparkles
---

# Features

An overview of what Nyctea provides.

## Lazy by default

All pipeline phases operate on Polars `LazyFrame`.
The data is never collected inside the validator unless you set `lazy=False`.
Error reporting uses targeted collects of only the columns it needs.

```python
result = schema.validate(df, registry)        # result.data is a LazyFrame
result = schema.validate(df, registry, lazy=False)  # result.data is a DataFrame
```

## Composable pipeline

Validation runs through ordered phases. Each phase receives a `PipelineContext` and returns it with updated state.

| Phase                   | Purpose                                                   |
| ----------------------- | --------------------------------------------------------- |
| `ColumnResolutionPhase` | Map synonyms to canonical column names                    |
| `ColumnParsingPhase`    | Apply column-level transformations (strip, lower, to_int) |
| `CoercionPhase`         | Cast columns to target dtypes                             |
| `ColumnCheckPhase`      | Evaluate validation rules as boolean mask columns         |

Phases can be added, removed, or reordered.

## Plugin registry

Parsers and checks are registered by name in a `Registry`. One registry can be shared across many schemas.

```python
from nyctea import Registry, register_builtins

registry = Registry()
register_builtins(registry)  # strip, lower, upper, to_int, to_float, min_value, between, in_set, unique
```

Custom plugins can be added via OOP classes or the decorator API:

```python
from nyctea.plugins.decorators import ValidatorDecorator

decorators = ValidatorDecorator(registry)

@decorators.column_check(name="positive", description="Value must be > 0")
def positive(column: pl.Expr) -> pl.Expr:
    return column > 0
```

## Schema definition

Schemas are defined as Python dicts or YAML. Each column specifies a dtype, nullability, parsers, and checks.

```python
schema = SchemaModel.from_dict({
    "coerce": True,
    "on_failure": "null",
    "columns": {
        "age": {
            "dtype": "Int64",
            "nullable": True,
            "parsers": [{"name": "strip"}, {"name": "to_int"}],
            "checks": [{"name": "min_value", "args": {"min": 0}}],
        },
        "name": {
            "dtype": "Utf8",
            "nullable": False,
            "synonyms": ["Name", "NAME"],
        },
    }
})
```

## Failure handling

The `on_failure` field controls what happens when validation fails. Set it at schema level or per column.

| Value             | Behavior                                              |
| ----------------- | ----------------------------------------------------- |
| `raise` (default) | Raise `PipelineError` on failure                      |
| `null`            | Set failing values to null (requires `nullable=True`) |
| `ignore`          | Keep failing values as-is                             |

Per-column settings override the schema default:

```python
{
    "on_failure": "null",
    "columns": {
        "id": {"dtype": "Int64", "nullable": False, "on_failure": "raise"},
        "score": {"dtype": "Float64", "nullable": True},  # inherits "null"
    }
}
```

## Error reporting

`ErrorReportConfig` controls the detail level of the errors DataFrame returned by `validate()`.

### Summary mode (default)

One row per failing check with a count.

```text
column | check     | count
age    | min_value | 5
```

### Rows mode

Adds a list of failing row indices.

```text
column | check     | count | row_indices
age    | min_value | 5     | [0, 3, 7, 12, 15]
```

### Cells mode

One row per failing cell with the actual value.

```text
column | check     | row_index | value
age    | min_value | 0         | -5
age    | min_value | 3         | -1
```

Use `limit` to cap the number of error entries per column+check:

```python
config = ErrorReportConfig(mode="cells", limit=100)
result = schema.validate(df, registry, error_report_config=config)
```

## Coercion

When `coerce=True`, columns are cast to their target dtype before checks run. Failed casts are handled according to `on_failure`.

Per-column overrides are supported:

```python
{
    "coerce": False,
    "columns": {
        "age": {"dtype": "Int64", "coerce": True},   # coerced
        "name": {"dtype": "Utf8"},                     # not coerced
    }
}
```

## Column synonyms

Columns can have synonyms for automatic renaming.
If a synonym matches a column in the input data, it is renamed to the canonical name.

```python
"name": {"dtype": "Utf8", "synonyms": ["Name", "NAME", "full_name"]}
```

Ambiguous matches (both canonical and synonym present) raise `SchemaResolutionError`.
