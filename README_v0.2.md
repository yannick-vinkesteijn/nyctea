# Nyctea v0.2 - Plugin-Based Validation

> **Polars-based data validation library with an extensible OOP plugin architecture**

## What's New in v0.2

Nyctea v0.2 introduces a complete architectural refactor:

### 🔌 Plugin System
- **Extensible**: Create custom parsers and checks by inheriting from base classes
- **Type-safe**: Generic plugin classes with runtime validation
- **Discoverable**: Tag-based plugin discovery and registration

### 🔧 Customizable Pipeline
- **Flexible**: Add, remove, or reorder validation phases
- **Validated**: Strict dependency enforcement prevents invalid configurations
- **Observable**: Built-in logging and metrics collection

### 🎯 Schema-Centric API
- **Intuitive**: `schema.validate(df, registry)` - the schema owns validation
- **Pythonic**: Clean, object-oriented design
- **Production-ready**: Comprehensive error handling and logging

---

## Quick Start

### Installation

```bash
pip install nyctea
# or with uv
uv add nyctea
```

### Basic Usage

```python
import polars as pl
from nyctea import SchemaModel, MasterRegistry, register_builtins

# Define schema
schema = SchemaModel.from_dict({
    "columns": {
        "name": {
            "dtype": "Utf8",
            "parsers": [{"name": "strip"}, {"name": "lower"}],
            "nullable": False,
        },
        "age": {
            "dtype": "Int64",
            "parsers": [{"name": "to_int"}],
            "checks": [{"name": "min_value", "args": {"min": 0}}],
            "nullable": False,
        },
    }
})

# Register built-in plugins
registry = MasterRegistry()
register_builtins(registry)

# Load and validate data
df = pl.read_csv("data.csv")
result = schema.validate(df, registry)

# Inspect results
print(result.report.summary())
print(result.data)
```

---

## Creating Custom Plugins

### Custom Parser (OOP)

```python
from nyctea.plugins.column import ColumnParser
from nyctea.plugins.base import PluginMetadata
import polars as pl

class TrimParser(ColumnParser):
    def __init__(self):
        super().__init__(PluginMetadata(
            name="trim",
            description="Remove whitespace",
            tags=["string", "cleaning"]
        ))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        return column.str.strip_chars()

    def validate_args(self, **kwargs) -> None:
        pass  # No arguments

# Register
registry.register_column_parser(TrimParser())
```

### Custom Check (Functional)

```python
from nyctea.plugins.decorators import PluginDecorator
import polars as pl

decorators = PluginDecorator(registry)

@decorators.column_check(name="positive", tags=["numeric"])
def is_positive(column: pl.Expr) -> pl.Expr:
    return column > 0
```

---

## Pipeline Customization

```python
from nyctea.engine.pipeline import PipelinePhase, PhaseType
from nyctea.engine.context import PipelineContext

# Define custom phase
class AuditPhase(PipelinePhase):
    def __init__(self):
        super().__init__(
            name="audit",
            phase_type=PhaseType.REPORTING,
            dependencies=["column_checks"]
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        # Custom audit logic
        print(f"Audit: {len(context.check_failures)} failures")
        return context

# Customize pipeline
validator = schema.create_validator(registry)
validator.pipeline.add_phase(AuditPhase(), after="column_checks")
result = validator.validate(df)
```

---

## Built-in Plugins

### Parsers
- `strip` - Remove whitespace
- `to_int` - Convert to integer
- `to_float` - Convert to float
- `lower` - Convert to lowercase
- `upper` - Convert to uppercase

### Checks
- `between` - Value in range (min, max)
- `in_set` - Value in allowed set
- `min_value` - Value >= minimum
- `unique` - All values unique

---

## Architecture

```
BasePlugin[TInput, TOutput]
├── ColumnPlugin[pl.Expr, pl.Expr]
│   ├── ColumnParser (transformations)
│   └── ColumnCheck (validations)
└── FramePlugin[pl.LazyFrame, pl.LazyFrame]
    ├── FrameParser (transformations)
    └── FrameCheck (validations)

MasterRegistry
├── column_parsers: PluginRegistry[ColumnParser]
├── column_checks: PluginRegistry[ColumnCheck]
├── frame_parsers: PluginRegistry[FrameParser]
└── frame_checks: PluginRegistry[FrameCheck]

ValidationPipeline
├── ColumnResolutionPhase (synonyms)
├── ColumnParsingPhase (transformations)
└── ColumnCheckPhase (validations)
```

---

## Features

### ✅ Implemented (v0.2 MVP)
- Plugin system with base classes
- Type-safe registries
- Customizable validation pipeline
- Dependency enforcement
- Observability hooks (logging, metrics)
- Schema-centric API
- Built-in parsers and checks
- Column purity enforcement
- Frame shape preservation

### 🚧 Coming Soon (v0.2 Full)
- Complete pipeline phases (11 total)
- Frame parser/check support
- Comprehensive error reporting
- Reader plugins (CSV, Parquet)
- Streaming validation
- Full test suite
- Performance benchmarks

---

## Examples

See `test_minimal.py` for a working example.

Full Titanic example coming in next sprint (requires frame parser support).

---

## Migration from v0.1

### Old API
```python
from nyctea.engine import validate
from nyctea.functions import FunctionRegistry

result = validate(df, schema, registry)
```

### New API
```python
from nyctea import SchemaModel, MasterRegistry, register_builtins

schema = SchemaModel.from_yaml("schema.yaml")
registry = MasterRegistry()
register_builtins(registry)

result = schema.validate(df, registry)
```

---

## Documentation

- [Refactor Summary](REFACTOR_SUMMARY.md) - Complete implementation details
- [Refactor Plan](docs/nyctea-refactor-plan.md) - Original design document

---

## Development

### Testing

```bash
# Run minimal test
uv run python test_minimal.py

# Run linter
uv run ruff check src/nyctea/
```

### Contributing

1. Create custom plugins by inheriting from base classes
2. Add phases by implementing `PipelinePhase`
3. Follow Google-style docstrings
4. Ensure Ruff linting passes

---

## License

MIT

---

## Status

**v0.2 MVP: ✅ Complete**
- Core plugin system implemented
- Minimal working pipeline
- Schema-centric API functional

**v0.2 Full: 🚧 In Progress**
- Additional pipeline phases
- Frame plugin support
- Comprehensive testing

See [REFACTOR_SUMMARY.md](REFACTOR_SUMMARY.md) for detailed status.
