# Quick Start

Get started with Nyctea in 5 minutes.

## Installation

```bash
pip install nyctea
```

Or with uv:

```bash
uv add nyctea
```

## Basic Example

Let's validate a simple DataFrame:

```python
import polars as pl
from nyctea import validate, SchemaModel
from nyctea.functions import FunctionRegistry

# 1. Create a function registry
registry = FunctionRegistry()

# 2. Register a validation check
@registry.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    """Check that values are positive."""
    return col.gt(0)

# 3. Define a schema
schema = SchemaModel.from_dict({
    "columns": {
        "age": {
            "dtype": "Int64",
            "nullable": False,  # No nulls allowed
            "checks": [{"name": "positive"}]  # Must be positive
        },
        "name": {
            "dtype": "Utf8",
            "nullable": False  # No nulls allowed
        }
    }
})

# 4. Create some data
df = pl.DataFrame({
    "age": [25, -5, 30, None],
    "name": ["Alice", "Bob", "Carol", "Dave"]
})

# 5. Validate!
result = validate(df, schema, registry)

# 6. Check results
print(result.report.summary())
# Validation Report (Profile: strict)
# Rows: 2/4 valid (50.0%)
#
# Column Issues:
#   age:
#     Check failures: 1
#     Final nulls: 1

print(result.errors)
# shape: (2, 3)
# ┌────────┬──────────┬───────┐
# │ column ┆ check    ┆ count │
# │ ---    ┆ ---      ┆ ---   │
# │ str    ┆ str      ┆ u32   │
# ╞════════╪══════════╪═══════╡
# │ age    ┆ positive ┆ 1     │
# │ age    ┆ non_null ┆ 1     │
# └────────┴──────────┴───────┘
```

## Understanding the Results

Nyctea returns a `ValidationResult` with three components:

1. **`result.data`** - The validated DataFrame (or LazyFrame)
1. **`result.errors`** - A DataFrame listing all validation failures
1. **`result.report`** - Comprehensive validation statistics

### Validation Report

The report provides high-level statistics:

```python
result.report.rows_processed  # Total rows: 4
result.report.rows_valid      # Valid rows: 2
result.report.profile_used    # "strict"
```

Per-column statistics:

```python
for col_name, stats in result.report.columns.items():
    print(f"{col_name}:")
    print(f"  Check failures: {stats.check_failures}")
    print(f"  Nullified: {stats.nullified}")
    print(f"  Final nulls: {stats.final_null_count}")
```

## Using YAML Schemas

For larger schemas, use YAML:

**schema.yaml:**

```yaml
columns:
  age:
    dtype: Int64
    nullable: false
    checks:
      - name: positive
  name:
    dtype: Utf8
    nullable: false
```

**Python:**

```python
schema = SchemaModel.from_yaml_file("schema.yaml")
result = validate(df, schema, registry)
```

## Lenient Mode

Want to clean data instead of failing on errors?

```python
schema = SchemaModel.from_dict({
    "profile": "clean",  # Use lenient mode
    "columns": {
        "age": {
            "dtype": "Int64",
            "nullable": True,  # Required for lenient mode
            "checks": [{"name": "positive"}]
        }
    }
})

result = validate(df, schema, registry)
# Negative ages are set to null instead of failing
print(result.data["age"])
# [25, null, 30, null]
```

## Next Steps

- Learn about [validation profiles](profiles.md)
- Understand the [validation pipeline](pipeline.md)
- Write [custom functions](custom-functions.md)
- Explore [examples](examples.md)
