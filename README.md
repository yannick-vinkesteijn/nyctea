<img align="center" width="150" height="150" src="https://nyctea.vinkesteijn.io/assets/logo-nyctea.png" alt="Nyctea logo">

# Nyctea

[![PyPI](https://img.shields.io/pypi/v/nyctea.svg)](https://pypi.org/project/nyctea/)
[![Python versions](https://img.shields.io/pypi/pyversions/nyctea.svg)](https://pypi.org/project/nyctea/)
[![License](https://img.shields.io/pypi/l/nyctea.svg)](https://github.com/yannick-vinkesteijn/nyctea/blob/main/LICENSE)
[![CI](https://github.com/yannick-vinkesteijn/nyctea/actions/workflows/ci.yaml/badge.svg)](https://github.com/yannick-vinkesteijn/nyctea/actions/workflows/ci.yaml)

Polars-based data validation library with an extensible OOP validator architecture.

## Features

### Validator system

- **Extensible**: create custom parsers and checks by inheriting from base classes
- **Type-safe**: generic validator classes with runtime validation
- **Discoverable**: tag-based validator discovery and registration

### Customizable pipeline

- **Flexible**: add, remove, or reorder validation phases
- **Validated**: strict dependency enforcement prevents invalid configurations
- **Observable**: built-in logging and metrics collection

### Schema-centric API

- **Intuitive**: `schema.validate(df, registry)`, the schema owns validation
- **Pythonic**: clean, object-oriented design
- **Out-of-core**: built on Polars `LazyFrame`, designed for larger-than-RAM data

## Installation

```bash
pip install nyctea
# or with uv
uv add nyctea
```

## Quick start

```python
import polars as pl
from nyctea import Registry, SchemaModel, register_builtins

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

# Register built-in validators
registry = Registry()
register_builtins(registry)

# Load and validate data
df = pl.scan_csv("data.csv")
result = schema.validate(df, registry)

# Inspect results
print(result.report.summary())
print(result.data.collect())
```

## Creating custom validators

### Custom parser (OOP)

```python
import polars as pl
from nyctea.validators import ColumnParser, ValidatorMetadata


class TrimParser(ColumnParser):
    def __init__(self):
        super().__init__(ValidatorMetadata(
            name="trim",
            description="Remove whitespace",
            tags=["string", "cleaning"],
        ))

    def execute(self, column: pl.Expr, **kwargs) -> pl.Expr:
        return column.str.strip_chars()

    def validate_args(self, **kwargs) -> None:
        pass  # No arguments


registry.register_column_parser(TrimParser())
```

### Custom check (functional)

```python
import polars as pl
from nyctea import checker, frame_checker, frame_parser, parser



@checker(registry=registry, name="positive", tags=["numeric"])
def is_positive(column: pl.Expr) -> pl.Expr:
    return column > 0
```

## Architecture

```text
Validator[TInput, TOutput]
├── ColumnValidator[pl.Expr, pl.Expr]
│   ├── ColumnParser (transformations)
│   └── ColumnCheck (validations)
└── FrameValidator[pl.LazyFrame, pl.LazyFrame]
    ├── FrameParser (transformations)
    └── FrameCheck (validations)

Registry
├── column_parsers: ValidatorRegistry[ColumnParser]
├── column_checks: ValidatorRegistry[ColumnCheck]
├── frame_parsers: ValidatorRegistry[FrameParser]
└── frame_checks: ValidatorRegistry[FrameCheck]

ValidationPipeline
├── ColumnResolutionPhase (synonyms)
├── ColumnParsingPhase (transformations)
├── CoercionPhase (dtype coercion)
└── ColumnCheckPhase (checks, nullable enforcement)
```

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=src/nyctea --cov-report=term --cov-report=html
uv run ruff check src/ tests/
uv run ty check src/nyctea
```

CI runs linting, type checking, and the test suite on Python 3.11 through 3.14 for every pull request.

## Documentation

- **[Quickstart](https://nyctea.vinkesteijn.io/user-guide/quickstart/)**: getting started guide
- **[Features](https://nyctea.vinkesteijn.io/user-guide/features/)**: schema syntax and validator capabilities
- **[Registry guide](https://nyctea.vinkesteijn.io/user-guide/registry/)**: registering and discovering validators
- **[API reference](https://nyctea.vinkesteijn.io/api/)**: full public API
- **[Breaking changes](https://nyctea.vinkesteijn.io/releases/breaking-changes/)**: migrating between versions

## Contributing

Contributions are welcome. Open an issue before starting anything beyond a trivial fix; see
[docs/development/contributing.md](https://nyctea.vinkesteijn.io/development/contributing/) for the full workflow
(issue-first, branch and PR conventions, CI overview) and
[DEVELOPMENT.md](<%5BDEVELOPMENT.md%5D(https://github.com/yannick-vinkesteijn/nyctea/blob/main/DEVELOPMENT.md)>) for local setup.

## License

MIT
