# Function Registry

The Function Registry is the heart of Nyctea's extensibility. It allows you to register custom parsers and validation
checks that are used during the validation pipeline.

## Overview

The `FunctionRegistry` class manages four types of functions:

| Function Type     | Purpose                 | Input          | Output           | Row Count Preserved |
| ----------------- | ----------------------- | -------------- | ---------------- | ------------------- |
| **Column Parser** | Transform column values | `pl.Expr`      | `pl.Expr`        | N/A                 |
| **Column Check**  | Validate column values  | `pl.Expr`      | `pl.Expr` (bool) | N/A                 |
| **Frame Parser**  | Transform DataFrames    | `pl.LazyFrame` | `pl.LazyFrame`   | Yes                 |
| **Frame Check**   | Validate DataFrames     | `pl.LazyFrame` | `pl.LazyFrame`   | Yes                 |

## Creating a Registry

```python
from nyctea.functions import FunctionRegistry

registry = FunctionRegistry()
```

## Column Parsers

Column parsers transform individual column values. Common use cases include:

- String normalization (trim, case conversion)
- Date parsing
- Unit conversions
- Data cleaning

### Basic Column Parser

```python
import polars as pl

@registry.column_parser(name="trim")
def trim_whitespace(col: pl.Expr) -> pl.Expr:
    """Remove leading/trailing whitespace."""
    return col.str.strip_chars()
```

### Column Parser with Parameters

```python
@registry.column_parser(name="replace_text")
def replace_text(col: pl.Expr, old: str, new: str) -> pl.Expr:
    """Replace text in column values.

    Args:
        col: Input column expression
        old: Text to replace
        new: Replacement text

    Returns:
        Column with replacements applied
    """
    return col.str.replace(old, new)
```

Use in schema:

```yaml
columns:
  description:
    dtype: Utf8
    parsers:
      - name: replace_text
        args:
          old: "N/A"
          new: ""
```

## Column Checks

Column checks validate individual column values. They must return a boolean expression.

### Basic Column Check

```python
@registry.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    """Check that values are positive."""
    return col.gt(0)
```

### Column Check with Parameters

```python
@registry.column_check(name="in_range")
def in_range(col: pl.Expr, min_val: float, max_val: float) -> pl.Expr:
    """Check that values fall within a range.

    Args:
        col: Input column expression
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)

    Returns:
        Boolean expression indicating which values are in range
    """
    return col.is_between(min_val, max_val)
```

Use in schema:

```yaml
columns:
  temperature:
    dtype: Float64
    checks:
      - name: in_range
        args:
          min_val: -40
          max_val: 85
```

## Frame Parsers

Frame parsers transform entire DataFrames. They must preserve the row count and column set.

### Basic Frame Parser

```python
@registry.frame_parser(name="sort_by_date")
def sort_by_date(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Sort DataFrame by date column."""
    return lf.sort("date")
```

### Frame Parser with Parameters

```python
@registry.frame_parser(name="fill_nulls")
def fill_nulls(lf: pl.LazyFrame, column: str, value: any) -> pl.LazyFrame:
    """Fill nulls in a specific column.

    Args:
        lf: Input LazyFrame
        column: Column name to fill
        value: Value to use for filling

    Returns:
        LazyFrame with nulls filled
    """
    return lf.with_columns(pl.col(column).fill_null(value))
```

Use in schema:

```yaml
frame_parsers:
  - name: sort_by_date
  - name: fill_nulls
    args:
      column: "status"
      value: "unknown"
```

## Frame Checks

Frame checks validate entire DataFrames. They must preserve the row count and column set, but can raise exceptions
on validation failure.

### Basic Frame Check

```python
@registry.frame_check(name="min_rows")
def min_rows(lf: pl.LazyFrame, count: int) -> pl.LazyFrame:
    """Ensure DataFrame has minimum row count.

    Args:
        lf: Input LazyFrame
        count: Minimum required rows

    Returns:
        Input LazyFrame if check passes

    Raises:
        ValueError: If row count is below minimum
    """
    actual_count = lf.select(pl.len()).collect().item()
    if actual_count < count:
        raise ValueError(f"Frame has {actual_count} rows, minimum is {count}")
    return lf
```

## Validation Rules

The registry enforces strict rules to ensure correctness:

### Type Safety

All parameters and returns must be type-annotated:

```python
# ✅ Good
@registry.column_parser(name="trim")
def trim(col: pl.Expr) -> pl.Expr:
    return col.str.strip_chars()

# ❌ Bad - missing annotations
@registry.column_parser(name="trim")
def trim(col):
    return col.str.strip_chars()
```

### Column Purity

Column functions can only reference their input column:

```python
# ✅ Good - only references input column
@registry.column_parser(name="normalize")
def normalize(col: pl.Expr) -> pl.Expr:
    return (col - col.mean()) / col.std()

# ❌ Bad - references other column
@registry.column_parser(name="ratio")
def ratio(col: pl.Expr) -> pl.Expr:
    return col / pl.col("total")  # References "total" column
```

### JSON-Serializable Defaults

Default parameter values must be JSON-serializable:

```python
# ✅ Good
@registry.column_check(name="min_length")
def min_length(col: pl.Expr, length: int = 5) -> pl.Expr:
    return col.str.len_chars().ge(length)

# ❌ Bad - datetime not JSON-serializable
from datetime import datetime
@registry.column_check(name="after_date")
def after_date(col: pl.Expr, date: datetime = datetime.now()) -> pl.Expr:
    return col.gt(date)
```

### No Variadic Args

Functions cannot use `*args` or `**kwargs`:

```python
# ✅ Good
@registry.column_check(name="in_list")
def in_list(col: pl.Expr, values: list) -> pl.Expr:
    return col.is_in(values)

# ❌ Bad - uses **kwargs
@registry.column_check(name="in_list")
def in_list(col: pl.Expr, **kwargs) -> pl.Expr:
    return col.is_in(kwargs["values"])
```

## Error Messages

The registry provides clear error messages when validation fails:

```python
# Missing type annotation
@registry.column_parser(name="bad_func")
def bad_func(col):  # Missing return type
    return col.str.upper()

# RegistryError: column parser 'bad_func' must return pl.Expr
```

```python
# Violates column purity
@registry.column_parser(name="bad_func")
def bad_func(col: pl.Expr) -> pl.Expr:
    return col / pl.col("other")

# ColumnPurityError: column parser 'bad_func' referenced disallowed columns: other
```

## Reusing Functions Across Registries

You can register the same function in multiple registries:

```python
registry1 = FunctionRegistry()
registry2 = FunctionRegistry()

def positive(col: pl.Expr) -> pl.Expr:
    return col.gt(0)

registry1.register_column_check(positive, name="positive")
registry2.register_column_check(positive, name="positive")
```

Or use the decorator with explicit names:

```python
@registry1.column_check(name="positive")
@registry2.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    return col.gt(0)
```

## Best Practices

1. **Use descriptive names** - Function names should clearly describe what they do
1. **Add docstrings** - Document parameters, return values, and behavior
1. **Keep functions pure** - Column functions should only depend on their input
1. **Validate parameters** - Check parameter values and raise clear errors
1. **Test thoroughly** - Write unit tests for custom functions
1. **Use type hints** - Always provide complete type annotations

## Next Steps

- Learn about [column parsers](column-parsers.md) in detail
- Explore [column checks](column-checks.md) patterns
- See [custom functions](custom-functions.md) for advanced examples
