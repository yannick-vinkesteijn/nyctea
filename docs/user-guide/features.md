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

## Streaming engine for internal aggregates

Validation's internal aggregate collects (check and coercion enforcement, summary error counts, report building) are pure reductions: sums, lengths, boolean `all()`.
Above `schema.streaming_row_threshold` rows, they use Polars' streaming engine, which cuts peak memory substantially on large data.
Below it, they use the default engine, since streaming has a fixed per-query setup cost that outweighs the reduction itself on small data.
The default threshold is 100,000 rows, based on a measured crossover.
Override it per schema if your workload sits far from that:

```python
schema = SchemaModel.from_dict({
    "streaming_row_threshold": 10_000,  # lower it if you mostly validate large files
    "columns": {"age": {"dtype": "Int64"}},
})
```

A `LazyFrame` input always uses streaming, since its row count isn't known without collecting, and passing lazy input in the first place signals larger or out-of-core data.

The `rows` and `cells` error report modes are the exception.
They materialise row indices and failing values rather than reducing them, so the threshold does not apply to them and they pass no `engine=` at all.
That leaves them on Polars' own default selection, `engine="auto"`, which means they do follow your global affinity setting where the aggregates below deliberately do not.
Only the `summary` mode's error counts are an aggregate.

These aggregate collects always pass an explicit `engine=` value, so they don't respect [`pl.Config.set_engine_affinity()`](https://docs.pola.rs/api/python/stable/reference/api/polars.Config.set_engine_affinity.html) or the `POLARS_ENGINE_AFFINITY` environment variable, unlike `engine="auto"` calls elsewhere in your own code.
That is deliberate.
`streaming_row_threshold` is a per-query decision that knows how much data it is looking at, while Polars' engine affinity is a single global switch with no size awareness (see the `engine` parameter on [`LazyFrame.collect`](https://docs.pola.rs/api/python/stable/reference/lazyframe/api/polars.LazyFrame.collect.html)).
If your global affinity is set to `"streaming"`, nyctea's internal aggregates on small data still use the in-memory engine unless you lower `streaming_row_threshold` yourself.
The `rows` and `cells` collects described above are the ones that will follow it, since they leave the choice to Polars.

## Composable pipeline

Validation runs through ordered phases. Each phase receives a `PipelineContext` and returns it with updated state.

| Phase                   | Purpose                                                   |
| ----------------------- | --------------------------------------------------------- |
| `ColumnResolutionPhase` | Map synonyms to canonical column names                    |
| `ColumnParsingPhase`    | Apply column-level transformations (strip, lower, to_int) |
| `CoercionPhase`         | Cast columns to target dtypes                             |
| `ColumnCheckPhase`      | Evaluate validation rules as boolean mask columns         |
| `NotNullPhase`          | Enforce `nullable: false` against the final column        |

Phases can be added, removed, or reordered, including `CoercionPhase` relative to parsing and checks: a check written against raw strings can run before coercion, one written against typed values can run after.
Two positions are fixed.
`ColumnResolutionPhase` always runs first, since every other phase reads resolved names.
`NotNullPhase` always runs last, since it answers "does the output contain nulls", which only means something once everything that could introduce one has already run.
`ValidationPipeline` rejects any ordering that violates either.

## Validator registry

Parsers and checks are registered by name in a `Registry`. One registry can be shared across many schemas.

```python
from nyctea import Registry, register_builtins

registry = Registry()
register_builtins(registry)  # strip, lower, upper, to_int, to_float, min_value, between, in_set, unique
```

Custom validators can be added via OOP classes or the decorator API:

```python
from nyctea import checker, frame_checker, frame_parser, parser


@checker(registry=registry, name="positive", description="Value must be > 0")
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

## Frame-level parsers and checks

Column parsers and checks operate on one column at a time. Frame parsers and checks
operate on the whole DataFrame, for rules that need to see more than one column, such
as cross-column comparisons or a minimum row count.

```python
from nyctea import checker, frame_checker, frame_parser, parser


@frame_checker(registry=registry, name="min_rows")
def min_rows(frame: pl.LazyFrame, min_rows: int = 1) -> pl.LazyFrame:
    if frame.select(pl.len()).collect().item() < min_rows:
        raise ValueError(f"expected at least {min_rows} rows")
    return frame

schema = SchemaModel.from_dict({
    "frame_checks": [{"name": "min_rows", "args": {"min_rows": 2}}],
    "columns": {"age": {"dtype": "Int64"}},
})
```

Frame checks must preserve row count and the set of columns, and raise on failure.
Column order and values are not checked, so a well-behaved frame check should not
change them even though nothing currently enforces it. Frame parsers may add, drop,
or reorder columns and rows, and run before column parsers so later steps see the
transformed frame.

## Failure handling

The `on_failure` field controls what happens when validation fails. Set it at schema level or per column.

| Value             | Behavior                         |
| ----------------- | --------------------------------- |
| `raise` (default) | Raise `PipelineError` on failure |
| `null`            | Set failing values to null       |
| `ignore`          | Keep failing values as-is        |

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

`on_failure: "null"` is legal on a non-nullable column.
A resulting not-null violation is reported rather than raised, the same way `on_failure: "ignore"` behaves.

### Which exception you get

`schema.validate` raises three kinds of error, and the distinction is about whose problem it is.

`ConfigurationError` means the schema itself does not hold up.
A check or parser it names is not in the registry, an argument does not bind, or a column declares the same check twice.
This is checked before any data is read, so it comes first and does not depend on the data at all.

`ValidationError` means your input does not have the structure the schema describes.
A required column is missing from the input, or a name resolves ambiguously because both the canonical name and a synonym are present.
Nyctea cannot start validating, because it cannot tell which column is which.
This covers resolving the columns you passed in.
A frame parser that removes a required column mid-run is reported as `PipelineError`, because by then validation had started.

`PipelineError` covers the rest of a validation run.
That means a check, parser, coercion or nullability failure on a column set to `on_failure: "raise"`, and a phase that failed while building its part of the query.
When a phase fails unexpectedly, the original exception is kept as the `__cause__`.

`ValidationError` and `PipelineError` carry a `phase` attribute, and a `column` whenever one column owns the failure.
Expect `column` to be `None` for a failure that belongs to the frame rather than to any single column.
`ConfigurationError` carries neither, because it is raised against the schema before any phase has run.

```python
from nyctea import ConfigurationError, PipelineError, ValidationError

try:
    result = schema.validate(df, registry)
except ConfigurationError as e:
    print(f"Schema does not verify against the registry: {e}")
except ValidationError as e:
    print(f"Schema does not fit the input: column {e.column!r} in phase {e.phase!r}")
except PipelineError as e:
    print(f"Validation stopped: column {e.column!r} in phase {e.phase!r}")
```

All three inherit from `NycteaError`, so catch that to handle any of them.

One case falls outside this contract.
Nyctea builds a lazy query and evaluates it in one pass, so a check or parser whose expression builds correctly but fails during evaluation surfaces as the underlying Polars exception rather than a `NycteaError`.
A check that casts with `strict=True` against a value that will not fit raises `polars.exceptions.InvalidOperationError`, for example.
Write checks that return a boolean expression over the column and leave failure handling to `on_failure`, rather than ones that raise on bad data.

A custom phase can raise `ValidationError` itself to report a structural problem of its own.
The pipeline passes it through untouched rather than wrapping it, which is how a phase you write says "this data cannot be validated" instead of "this phase broke".
Raising `PipelineError` directly works the same way and keeps the `phase` and `column` you set.
Any other exception a phase raises, from `execute` or from the `can_skip` and `can_change_row_count` hooks, is wrapped as `PipelineError` with the original kept as `__cause__`.

## Parser failures and null counts

A parser failure occurs when a non-null value becomes null anywhere across a
column's parser chain. Nyctea reports it under the reserved check name `parse`,
counts it in `report.columns[column].parse_failures`, and marks the row invalid.
Input values that were already null are not parser failures.

`original_null_count` counts nulls after synonyms are resolved but before frame
parsers and column parsers run. `final_null_count` counts nulls in the validated
output. A frame parser that filters rows can therefore make the original count
larger than the final row count.

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

Ambiguous matches (both canonical and synonym present) raise `ValidationError` from the column resolution phase.

### Cleaned column matching

Exact matching is the default and is unchanged.
Set `column_matching: cleaned` on the schema to also accept names that match after trimming whitespace and Unicode case folding, so ` AGE ` resolves to `age` without enumerating every casing as a synonym.

```yaml
column_matching: cleaned
columns:
  age:
    dtype: Int64
```

Exact matches always win over cleaned ones.
If two physical columns match one schema column at the cleaned level, that is ambiguous and resolution fails rather than guessing.
A schema whose accepted names collide once cleaned, such as a column `age` and a synonym `AGE` on a different column, is rejected when it is constructed.
