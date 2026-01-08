# Nyctea Documentation

This directory contains the source files for Nyctea's documentation, built with [Zensical](https://zensical.org/).

## Building the Documentation

### Prerequisites

Install Zensical:

```bash
pip install zensical mkdocstrings[python]
```

Or with uv:

```bash
uv add --dev zensical mkdocstrings-python
```

### Local Development

Serve the documentation locally with auto-reload:

```bash
zensical serve
```

Or with optional flags:

```bash
zensical serve --open  # Open browser automatically
zensical serve --dev-addr localhost:3000  # Use different port
```

Then open <http://localhost:8000> in your browser (or the custom port you specified).

### Building Static Site

Build the static documentation site:

```bash
zensical build
```

The built site will be in the `site/` directory.

## Documentation Structure

```text
docs/
├── index.md              # Homepage
├── api/                  # API reference (auto-generated from docstrings)
│   ├── index.md
│   ├── engine.md         # Validation engine
│   ├── registry.md       # Function registry
│   ├── schema.md         # Schema models
│   └── ingest.md         # Data ingestion
└── guides/               # User guides (manually written)
    ├── index.md
    ├── quickstart.md
    ├── registry.md
    └── ...
```

## Writing Documentation

### Module Docstrings

Module docstrings should use Google style:

```python
"""Brief description.

Extended description with more details.

Example:
    Usage example::

        from nyctea import validate
        result = validate(df, schema, registry)

Note:
    Important notes or warnings.

Args:
    param1: Description of param1.
    param2: Description of param2.

Returns:
    Description of return value.

Raises:
    ValueError: When something goes wrong.
"""
```

### Function Docstrings

Functions should also use Google style:

```python
def validate(df, schema, registry):
    """Validate a DataFrame according to schema.

    Args:
        df: Input DataFrame or LazyFrame.
        schema: SchemaModel defining validation rules.
        registry: FunctionRegistry with parsers and checks.

    Returns:
        ValidationResult with data, errors, and report.

    Raises:
        SchemaResolutionError: If columns cannot be resolved.

    Example:
        >>> result = validate(df, schema, registry)
        >>> print(result.report.summary())
    """
```

### Markdown Files

Guide pages use standard Markdown with some extensions:

- **Admonitions** for notes/warnings
- **Code blocks** with syntax highlighting
- **Tables** for structured data
- **Links** to other pages and API docs

Example:

````markdown
# Page Title

Brief introduction.

## Section

Content with **bold** and *italic*.

```python
# Code example
result = validate(df, schema, registry)
```

!!! note
    This is an admonition box.

See the [API reference](../api/index.md) for more details.
````

## API Reference

API reference pages use Zensical's `:::` syntax to auto-generate documentation from docstrings:

```markdown
# Module Name

## FunctionName

::: module.path.FunctionName
    options:
      show_root_heading: true
      heading_level: 3
```

Zensical will automatically extract docstrings, signatures, and type annotations.

## Tips

1. **Keep docstrings updated** - They're the source of truth for API docs
1. **Use examples** - Code examples in docstrings appear in the API reference
1. **Link liberally** - Link to related pages and API docs
1. **Test locally** - Always preview with `zensical serve` before committing
1. **Check links** - Zensical will warn about broken internal links

## Configuration

Documentation configuration is in `zensical.toml` at the project root. Key settings:

- **Theme** - Modern Material-inspired theme with dark mode
- **Features** - Code highlighting, copy buttons, search, navigation
- **Navigation** - Site structure defined in the `nav` array
- **Fonts** - Custom font configuration

## Contributing

When adding new modules or functions:

1. Add Google-style docstrings to the code
1. Add the module to `docs/api/` if needed
1. Update navigation in `zensical.toml`
1. Add user guide pages for major features
1. Test locally with `zensical serve`
1. Submit PR with both code and docs
