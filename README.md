# Nyctea

**Polars-based data validation library with an extensible OOP plugin architecture**

> **🤖 Claude Code Experiment**: This project was built as a "vibe code" experiment to explore transferring
> software engineering knowledge to Claude Code for production Python development. See
> [docs/development/](docs/development/) for the full development story, sprint notes, and lessons learned.

## Features

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

## Installation

```bash
pip install nyctea
# or with uv
uv add nyctea
```

## Quick Start

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

## Architecture

```text
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

See [docs/development/TESTING_COMPLETE.md](docs/development/TESTING_COMPLETE.md) for detailed test documentation.

### CI/CD

GitHub Actions run automatically on all PRs and pushes to main:

- Linting with Ruff
- Tests on Python 3.10, 3.11, 3.12
- Coverage reporting
- Type checking with mypy
- Pre-commit hooks validation

## Documentation

- **[Quick Reference](docs/QUICK_REFERENCE.md)** - API quick reference
- **[Development Docs](docs/development/)** - Sprint notes, architecture decisions, and lessons learned
- **[Refactor Plan](docs/nyctea-refactor-plan.md)** - Original architectural plan

## Status

**Current**: v0.2.0 MVP

- ✅ Core plugin system implemented
- ✅ 61 tests passing with 52% coverage
- ✅ GitHub Actions CI/CD configured
- 🚧 Additional phases and frame support in progress

## Contributing

Contributions are welcome! Please open an issue or pull request.

Guidelines:

1. Follow the OOP plugin architecture patterns
2. Add tests mirroring the `src/` structure
3. Ensure Ruff linting passes
4. Follow Google-style docstrings

## License

MIT
