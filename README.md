# Nyctea

Polars-optimized data validation library with Pydantic schemas based on packages like Pandera, Patito and Dataframely.

> **📢 Nyctea v0.2 is here!** A complete architectural refactor with an extensible plugin system, customizable
> validation pipeline, and schema-centric API. See [README_v0.2.md](README_v0.2.md) for the new API documentation.
> The v0.1 API (documented below) remains available.

______________________________________________________________________

## Version Status

- **v0.1** (this README): Stable, production-ready, functional API
- **v0.2** ([README_v0.2.md](README_v0.2.md)): New OOP plugin-based architecture
  - ✅ Core plugin system implemented
  - ✅ 61 tests passing with 52% coverage
  - ✅ GitHub Actions CI/CD configured
  - 🚧 Additional phases and frame support in progress

______________________________________________________________________

## Features

- **Flexible validation profiles**: Switch between strict validation and lenient sanitization
- **Observable outcomes**: Comprehensive validation reports track what was fixed, what failed, and what passed
- **Two orthogonal controls**: Separate `nullable` (data quality) from `on_failure` (processing behavior)
- **Auto-enforced nullability**: `nullable=False` is now automatically enforced
- **Predictable pipeline**: Fixed order ensures checks run on final dtypes

## Installation

```bash
pip install nyctea
```

## Quick Start

### Basic Validation (Strict Mode)

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

## Validation Pipeline

Nyctea uses a fixed, predictable pipeline order:

```text
1. Column resolution (synonym mapping)
2. Count original nulls
3. Frame parsers (DataFrame-level transformations)
4. Column parsers (string transformations)
5. COERCE (dtype casting) ← Moved before checks for cleaner semantics
6. Frame checks
7. Column checks (validation on coerced dtype)
   - Auto-inject non_null check if nullable=False
8. Build error report (captures ALL failures)
9. NULLIFY failures where on_failure="null"
10. Final nullable check (safety assertion)
11. Build validation report
12. Return (data + errors + report)
```

**Key insight**: Coercion happens BEFORE checks, so checks run on the final dtype (e.g., check `age > 0` on `Int64`,
not on string).

## Validation Profiles

Nyctea supports three validation profiles:

### Strict Profile (default)

All failures raise errors. This is the traditional validation behavior.

```yaml
profile: strict  # Can omit, it's the default
columns:
  age:
    dtype: Int64
    nullable: false  # Now actually enforced!
    checks:
      - name: positive
```

### Clean Profile

Lenient mode: nullify failures for nullable columns, raise for non-nullable.

```yaml
profile: clean
columns:
  age:
    dtype: Int64
    nullable: true  # Failures → null
    checks:
      - name: positive
  id:
    dtype: Utf8
    nullable: false  # Failures → error (even in clean mode)
    checks:
      - name: non_empty
```

### Audit Profile

Like strict, but with enhanced reporting (for tracking data quality issues).

```yaml
profile: audit
columns:
  age:
    dtype: Int64
    nullable: false
    checks:
      - name: positive
```

## Column-Level Control

Override profile defaults on a per-column basis using `on_failure`:

```yaml
profile: strict  # Default is strict
columns:
  age:
    dtype: Int64
    nullable: true
    on_failure: null  # Override: lenient for this column only
    checks:
      - name: positive
  name:
    dtype: Utf8
    nullable: false  # Follows profile: strict
```

## Configuration Rules

- `on_failure: "raise"` - Stop validation and report errors (default for strict)
- `on_failure: "null"` - Set failing values to null and continue (requires `nullable: true`)
- `on_failure: null` - Inherit from schema profile

**Important**: You cannot have `on_failure: "null"` with `nullable: false` - this is validated at schema parse time.

## Validation Reports

Every validation returns both an error DataFrame and a comprehensive report:

```python
result = validate(df, schema, registry)

# Traditional error DataFrame (backward compatible)
print(result.errors)
# ┌──────────┬───────────┬───────┐
# │ column   │ check     │ count │
# │ ---      │ ---       │ ---   │
# │ str      │ str       │ u32   │
# ╞══════════╪═══════════╪═══════╡
# │ age      │ positive  │ 5     │
# └──────────┴───────────┴───────┘

# New validation report
print(result.report.summary())
# Validation Report (Profile: clean)
# Rows: 95/100 valid (95.0%)
#
# Column Issues:
#   age:
#     Check failures: 5
#     Nullified: 5
#     Final nulls: 5

# Per-column stats
for col, stats in result.report.columns.items():
    print(f"{col}:")
    print(f"  Coercion failures: {stats.coercion_failures}")
    print(f"  Check failures: {stats.check_failures}")
    print(f"  Nullified: {stats.nullified}")
    print(f"  Final nulls: {stats.final_null_count}")
```

## Examples

### Example 1: Strict Validation

```python
schema = SchemaModel.from_dict({
    "profile": "strict",
    "columns": {
        "patient_id": {
            "dtype": "Utf8",
            "nullable": False,
            "checks": [{"name": "unique"}]
        },
        "age": {
            "dtype": "Int64",
            "nullable": False,
            "checks": [{"name": "between", "args": {"min": 0, "max": 120}}]
        }
    }
})

# This will raise on any validation failures
result = validate(df, schema, registry)
```

### Example 2: Lenient Sanitization

```python
schema = SchemaModel.from_dict({
    "profile": "clean",
    "columns": {
        "optional_age": {
            "dtype": "Int64",
            "nullable": True,  # Required for lenient mode
            "checks": [{"name": "positive"}]
        },
        "required_id": {
            "dtype": "Utf8",
            "nullable": False,  # Still strict for this column
        }
    }
})

result = validate(df, schema, registry)

# Negative ages → null (lenient)
# Missing IDs → error (strict)
print(result.report.summary())
```

### Example 3: Mixed Mode

```python
schema = SchemaModel.from_dict({
    "profile": "strict",  # Default is strict
    "columns": {
        "sensor_reading": {
            "dtype": "Float64",
            "nullable": True,
            "on_failure": "null",  # Override: lenient
            "checks": [{"name": "in_range", "args": {"min": -40, "max": 85}}]
        },
        "timestamp": {
            "dtype": "Datetime",
            "nullable": False,  # Follows profile: strict
        }
    }
})

# Out-of-range sensor readings → null
# Invalid timestamps → error
result = validate(df, schema, registry)
```

### Example 4: Coercion Strategy

```python
# Strict coercion: raise on failures
result = validate(df, schema, registry, coerce_strategy="strict")

# Lenient coercion: nullify on failures
result = validate(df, schema, registry, coerce_strategy="null_on_failure")

# Check what failed to coerce
for col, stats in result.report.columns.items():
    if stats.coercion_failures > 0:
        print(f"{col}: {stats.coercion_failures} coercion failures")
```

## Backward Compatibility

- Default `profile="strict"` preserves existing validation behavior
- Default `on_failure=None` inherits from profile
- Existing schemas work unchanged

**Breaking change** (justified):

- `nullable=False` is now automatically enforced (was documented but not implemented)
- This closes a gap between documentation and implementation

## Advanced Usage

### Custom Parsers

```python
@registry.column_parser(name="trim_whitespace")
def trim(col: pl.Expr) -> pl.Expr:
    return col.str.strip_chars()

@registry.column_parser(name="to_uppercase")
def uppercase(col: pl.Expr) -> pl.Expr:
    return col.str.to_uppercase()
```

### Custom Checks

```python
@registry.column_check(name="email_format")
def is_email(col: pl.Expr) -> pl.Expr:
    return col.str.contains(r"^[\w\.-]+@[\w\.-]+\.\w+$")

@registry.column_check(name="in_list")
def in_list(col: pl.Expr, values: list) -> pl.Expr:
    return col.is_in(values)
```

### Frame-Level Operations

```python
@registry.frame_parser(name="deduplicate")
def dedup(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.unique()

@registry.frame_check(name="min_rows")
def min_rows(lf: pl.LazyFrame, count: int) -> pl.LazyFrame:
    if lf.collect().height < count:
        raise ValueError(f"Frame has fewer than {count} rows")
    return lf
```

## Error Reporting Modes

Control error detail level:

```python
from nyctea.engine import ErrorReportConfig

# Summary mode (default) - just counts
config = ErrorReportConfig(mode="summary")
result = validate(df, schema, registry, error_report=config)

# Rows mode - counts + row indices
config = ErrorReportConfig(mode="rows", limit=100)
result = validate(df, schema, registry, error_report=config)

# Cells mode - individual failing cells with values
config = ErrorReportConfig(mode="cells", include_values=True, limit=10)
result = validate(df, schema, registry, error_report=config)
```

## Design Principles

1. **Two orthogonal knobs**: `nullable` (data quality requirement) ⊥ `on_failure` (processing behavior)
1. **Profile-based defaults**: Common patterns get names (`strict`/`clean`/`audit`)
1. **Column overrides profile**: Explicit `on_failure` at column level wins
1. **Observable outcomes**: Track what was nullified, what failed, what passed
1. **Predictable pipeline**: Fixed order, coercion before checks

## Testing

Nyctea has comprehensive test coverage with 61 tests across core modules:

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ --cov=src/nyctea --cov-report=term --cov-report=html

# Run specific test file
uv run pytest tests/plugins/test_registry.py -v

# Run with linting
uv run ruff check src/ tests/
uv run pytest tests/
```

### Test Coverage

- **Overall**: 52% coverage
- **Core modules**: Well-tested (78-96% coverage)
  - Plugin base: 89%
  - Plugin registry: 96%
  - Schema validator: 95%
  - Pipeline system: 78-88%
- **Legacy v0.1**: Lower coverage (will improve in future sprints)

See [TESTING_COMPLETE.md](TESTING_COMPLETE.md) for detailed test documentation.

### CI/CD

GitHub Actions run automatically on all PRs and pushes to main:

- Linting with Ruff
- Tests on Python 3.10, 3.11, 3.12
- Coverage reporting
- Type checking with mypy
- Pre-commit hooks validation

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or pull request.

When contributing to v0.2:

1. Follow the OOP plugin architecture patterns
1. Add tests mirroring the `src/` structure
1. Ensure Ruff linting passes
1. Follow Google-style docstrings
