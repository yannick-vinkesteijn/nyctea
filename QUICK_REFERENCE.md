# Nyctea v0.2 Quick Reference

## Installation & Setup

```python
from nyctea import SchemaModel, MasterRegistry, register_builtins

schema = SchemaModel.from_yaml("schema.yaml")
registry = MasterRegistry()
register_builtins(registry)
```

## Basic Validation

```python
import polars as pl

df = pl.read_csv("data.csv")
result = schema.validate(df, registry)

# Check results
print(result.report.summary())
print(result.data)       # Validated DataFrame
print(result.errors)      # Error summary
```

## Custom Column Parser

```python
from nyctea.plugins.column import ColumnParser
from nyctea.plugins.base import PluginMetadata
import polars as pl

class MyParser(ColumnParser):
    def __init__(self):
        super().__init__(PluginMetadata(name="my_parser"))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        # Your transformation logic
        return column.str.strip_chars()

    def validate_args(self, **kwargs) -> None:
        # Validate kwargs if needed
        pass

registry.register_column_parser(MyParser())
```

## Custom Column Check

```python
from nyctea.plugins.column import ColumnCheck
from nyctea.plugins.base import PluginMetadata
import polars as pl

class MyCheck(ColumnCheck):
    def __init__(self):
        super().__init__(PluginMetadata(name="my_check"))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        # Return boolean expression
        return column.str.len_chars() > 0

    def validate_args(self, **kwargs) -> None:
        pass

registry.register_column_check(MyCheck())
```

## Decorator-Style Plugin

```python
from nyctea.plugins.decorators import PluginDecorator
import polars as pl

decorators = PluginDecorator(registry)

@decorators.column_parser(name="trim", tags=["string"])
def trim(column: pl.Expr) -> pl.Expr:
    return column.str.strip_chars()

@decorators.column_check(name="positive", tags=["numeric"])
def positive(column: pl.Expr) -> pl.Expr:
    return column > 0
```

## Pipeline Customization

```python
from nyctea.engine.pipeline import PipelinePhase, PhaseType
from nyctea.engine.context import PipelineContext

class CustomPhase(PipelinePhase):
    def __init__(self):
        super().__init__(
            name="custom",
            phase_type=PhaseType.REPORTING,
            dependencies=["column_checks"]
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        # Your logic here
        print(f"Custom phase: {len(context.check_failures)} failures")
        return context

validator = schema.create_validator(registry)
validator.pipeline.add_phase(CustomPhase(), after="column_checks")
result = validator.validate(df)
```

## Observability

```python
from nyctea.engine.observability import LoggingObserver, MetricsCollector
from nyctea.engine.factory import create_minimal_pipeline

# Add observers
logger = LoggingObserver()
metrics = MetricsCollector()

pipeline = create_minimal_pipeline(observers=[logger, metrics])

# After validation
summary = metrics.get_summary()
print(summary)
```

## Schema YAML Format

```yaml
lazy: true
coerce: false
profile: strict  # strict, clean, or audit

columns:
  name:
    dtype: Utf8
    synonyms: [Name, NAME]
    parsers:
      - name: strip
      - name: lower
    checks:
      - name: in_set
        args:
          values: [alice, bob]
    required: true
    nullable: false

  age:
    dtype: Int64
    parsers:
      - name: to_int
    checks:
      - name: between
        args:
          min: 0
          max: 120
    required: true
    nullable: false
```

## Built-in Plugins

### Parsers
- `strip` - Remove whitespace
- `to_int` - Convert to Int64
- `to_float` - Convert to Float64
- `lower` - Lowercase string
- `upper` - Uppercase string

### Checks
- `between(min, max)` - Range check
- `in_set(values)` - Membership check
- `min_value(min)` - Minimum value
- `unique` - Uniqueness check

## Error Handling

```python
from nyctea import ValidationError, PipelineError

try:
    result = schema.validate(df, registry)
except ValidationError as e:
    print(f"Validation failed: {e}")
    print(f"Column: {e.column}")
    print(f"Phase: {e.phase}")
except PipelineError as e:
    print(f"Pipeline error: {e}")
    print(f"Phase: {e.phase}")
```

## Registry Inspection

```python
# Check what's registered
print(registry.get_plugin_counts())
# {'column_parsers': 5, 'column_checks': 4, ...}

# List all plugins
print(registry.column_parsers.list_names())
# ['strip', 'to_int', 'to_float', 'lower', 'upper']

# Get plugin by name
parser = registry.column_parsers.get("strip")
print(parser.metadata)
```

## Pipeline Inspection

```python
# List phases
print(validator.pipeline.list_phases())
# ['column_resolution', 'column_parsing', 'column_checks']

# Get pipeline info
print(len(validator.pipeline))  # Number of phases
print(validator.pipeline)  # Summary
```

## Common Patterns

### Load + Register + Validate

```python
schema = SchemaModel.from_yaml("schema.yaml")
registry = MasterRegistry()
register_builtins(registry)
result = schema.validate(df, registry)
```

### Custom Plugin + Use

```python
class EmailValidator(ColumnCheck):
    def __init__(self):
        super().__init__(PluginMetadata(name="email"))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        return column.str.contains(r'^.+@.+\..+$')

    def validate_args(self, **kwargs) -> None:
        pass

registry.register_column_check(EmailValidator())
```

### Pipeline Customization

```python
validator = schema.create_validator(registry)
validator.pipeline.add_phase(MyPhase(), after="column_parsing")
result = validator.validate(df)
```

## Troubleshooting

### Plugin Not Found
```python
# Error: KeyError: "No plugin named 'my_parser' registered"
# Solution: Register the plugin before validating
registry.register_column_parser(MyParser())
```

### Phase Dependency Error
```python
# Error: PipelineError: "Phase 'my_phase' depends on 'other_phase'"
# Solution: Ensure dependencies are specified correctly
class MyPhase(PipelinePhase):
    def __init__(self):
        super().__init__(
            name="my_phase",
            phase_type=PhaseType.CHECKING,
            dependencies=["column_parsing"]  # Add dependency
        )
```

### Purity Violation
```python
# Error: PluginExecutionError: "references multiple columns"
# Solution: Column plugins can only reference the input column
def bad_parser(column: pl.Expr) -> pl.Expr:
    return column / pl.col("total")  # ❌ References 'total'

def good_parser(column: pl.Expr) -> pl.Expr:
    return column * 2  # ✅ Only uses input column
```

## File Locations

```
src/nyctea/
├── __init__.py              # Main exports
├── exceptions.py            # Exception classes
├── plugins/
│   ├── base.py             # BasePlugin
│   ├── column.py           # Column plugin classes
│   ├── frame.py            # Frame plugin classes
│   ├── registry.py         # Registry classes
│   ├── decorators.py       # Decorator API
│   └── builtins/           # Built-in plugins
│       ├── parsers.py
│       ├── checks.py
│       └── register.py
├── engine/
│   ├── context.py          # PipelineContext
│   ├── pipeline.py         # ValidationPipeline
│   ├── phases.py           # Phase implementations
│   ├── factory.py          # Pipeline factory
│   └── observability.py    # Observers
├── schema/
│   ├── model.py            # SchemaModel
│   └── validator.py        # SchemaValidator
└── ingest/
    └── readers.py          # CSV/Parquet readers
```

## Next Steps

1. Read [REFACTOR_SUMMARY.md](REFACTOR_SUMMARY.md) for complete details
2. Read [README_v0.2.md](README_v0.2.md) for user guide
3. Run `test_minimal.py` to see it working
4. Create your own custom plugins
5. Experiment with pipeline customization
