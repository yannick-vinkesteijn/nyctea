# Validator Registry

The Registry is the heart of Nyctea's extensibility. It allows you to register custom parsers and validation
checks that are used during the validation pipeline.

## Overview

The `Registry` class manages four types of validators:

| Function Type     | Purpose                 | Input          | Output           | Row Count Preserved |
| ----------------- | ----------------------- | -------------- | ---------------- | ------------------- |
| **Column Parser** | Transform column values | `pl.Expr`      | `pl.Expr`        | N/A                 |
| **Column Check**  | Validate column values  | `pl.Expr`      | `pl.Expr` (bool) | N/A                 |
| **Frame Parser**  | Transform DataFrames    | `pl.LazyFrame` | `pl.LazyFrame`   | Yes                 |
| **Frame Check**   | Validate DataFrames     | `pl.LazyFrame` | `pl.LazyFrame`   | Yes                 |

## Creating a Registry

```python
from nyctea import Registry, ValidatorDecorator

registry = Registry()
decorators = ValidatorDecorator(registry)
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

@decorators.column_parser(name="trim")
def trim_whitespace(col: pl.Expr) -> pl.Expr:
    """Remove leading/trailing whitespace."""
    return col.str.strip_chars()
```

### Column Parser with Parameters

```python
@decorators.column_parser(name="replace_text")
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
@decorators.column_check(name="positive")
def positive(col: pl.Expr) -> pl.Expr:
    """Check that values are positive."""
    return col.gt(0)
```

### Column Check with Parameters

```python
@decorators.column_check(name="in_range")
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
@decorators.frame_parser(name="sort_by_date")
def sort_by_date(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Sort DataFrame by date column."""
    return lf.sort("date")
```

### Frame Parser with Parameters

```python
@decorators.frame_parser(name="fill_nulls")
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
@decorators.frame_check(name="min_rows")
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

## Registration rules

Names must be unique within each validator kind. Registering a second column check,
column parser, frame check, or frame parser under an existing name raises
`RegistrationError`.

Decorator functions receive a Polars expression or lazy frame and must return the
same kind of object. Schema arguments are forwarded as keyword arguments when the
validator executes.

## Best Practices

1. **Use descriptive names** - Function names should clearly describe what they do
1. **Add docstrings** - Document parameters, return values, and behavior
1. **Keep functions pure** - Column functions should only depend on their input
1. **Validate parameters** - Check parameter values and raise clear errors
1. **Test thoroughly** - Write unit tests for custom functions
1. **Use type hints** - Always provide complete type annotations

## Next Steps
