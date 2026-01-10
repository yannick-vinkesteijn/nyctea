# Nyctea Documentation

Polars-optimized data validation library with Pydantic schemas based on packages like Pandera, Patito and Dataframely.

## Overview

Nyctea provides a flexible, observable validation framework for Polars DataFrames with:

- **Flexible validation profiles** - Switch between strict validation and lenient sanitization
- **Observable outcomes** - Comprehensive validation reports track what was fixed, what failed, and what passed
- **Two orthogonal controls** - Separate `nullable` (data quality) from `on_failure` (processing behavior)
- **Auto-enforced nullability** - `nullable=False` is automatically enforced
- **Predictable pipeline** - Fixed order ensures checks run on final dtypes

## Quick Links

- [Installation](#installation)
- [Quick Start](guides/quickstart.md)
- [API Reference](api/index.md)
- [User Guides](guides/index.md)
- [Examples](guides/examples.md)

## Installation

```bash
pip install nyctea
```

Or with uv:

```bash
uv add nyctea
```

## Quick Example

```python
import polars as pl
from nyctea import validate, SchemaModel
from nyctea.functions import FunctionRegistry

# Define schema
schema = SchemaModel.from_dict({
    "columns": {
        "age": {
            "dtype": "Int64",
            "nullable": False,  # Auto-enforced!
            "checks": [{"name": "positive"}]
        },
        "name": {
            "dtype": "Utf8",
            "nullable": False
        }
    }
})

# Create function registry
registry = FunctionRegistry()

@registry.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    return col.gt(0)

# Validate data
df = pl.DataFrame({
    "age": [25, -5, 30],
    "name": ["Alice", "Bob", None]
})

result = validate(df, schema, registry)

# Check results
print(result.errors)  # Shows validation failures
print(result.report.summary())  # Human-readable summary
```

## Core Concepts

### Validation Pipeline

Nyctea uses a fixed, predictable pipeline order:

1. **Column resolution** - Map synonyms to canonical names
1. **Count original nulls** - Track initial data quality
1. **Frame parsers** - DataFrame-level transformations
1. **Column parsers** - String transformations per column
1. **Coercion** - Type casting (before checks!)
1. **Frame checks** - DataFrame-level validations
1. **Column checks** - Column-level validations
1. **Error reporting** - Capture all failures
1. **Nullification** - Apply lenient behavior where configured
1. **Final checks** - Safety assertions
1. **Report generation** - Build comprehensive validation report

### Validation Profiles

Three built-in profiles for common use cases:

- **strict** (default) - All failures raise errors
- **clean** - Nullify failures for nullable columns, raise for non-nullable
- **audit** - Like strict, but with enhanced reporting

### Column-Level Control

Override profile defaults per-column:

```yaml
profile: strict  # Default is strict
columns:
  age:
    dtype: Int64
    nullable: true
    on_failure: null  # Override: lenient for this column only
    checks:
      - name: positive
```

## Next Steps

- Read the [Quick Start Guide](guides/quickstart.md)
- Explore the [API Reference](api/index.md)
- Check out [Examples](guides/examples.md)
- Learn about [Function Registries](guides/registry.md)
