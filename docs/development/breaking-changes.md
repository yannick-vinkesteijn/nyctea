# Breaking Changes

## v0.1.0 → v0.2.0

### Summary

v0.2.0 introduces the OOP plugin system with a clean `Registry` class alongside the existing `FunctionRegistry`. The core `SchemaModel` is unchanged. No public API symbols that were exported in v0.1.0 have been removed.

The documented entry point shifted significantly. If you followed the v0.1.0 README or guides, you will need to update your code.

> **Note:** During pre-release development of v0.2.0, the registry class was temporarily named `MasterRegistry`. The final v0.2.0 release uses `Registry`, which is cleaner and less redundant. If you encountered `MasterRegistry` in any pre-release branch or documentation, replace it with `Registry`.

---

### What changed

#### Registry: `FunctionRegistry` → `Registry`

v0.1.0 used `FunctionRegistry` with decorator-based registration:

```python
from nyctea.functions.registry import FunctionRegistry

registry = FunctionRegistry()

@registry.column_parser(name="trim")
def trim(col: pl.Expr) -> pl.Expr:
    return col.str.strip_chars()
```

v0.2.0 introduces `Registry` with OOP plugin classes and a `register_builtins()` shortcut:

```python
from nyctea import Registry, register_builtins

registry = Registry()
register_builtins(registry)  # registers built-in parsers and checks
```

**`FunctionRegistry` still exists** as a top-level alias in `nyctea` (`from nyctea import FunctionRegistry`) for backward compatibility. Code using it will continue to import without error. But:

- It is a deprecated alias for `Registry`.
- It is no longer the recommended pattern.
- It does not work with the old `FunctionRegistry`-based decorator API from v0.1.0.

The alias will be removed in v0.3.0.

**Migration:** replace `FunctionRegistry` with `Registry`. Re-register custom functions using either OOP plugins or the `ValidatorDecorator` functional API.

#### Validation entry point

v0.1.0 used the standalone `validate()` function:

```python
from nyctea.engine.validate import validate

result = validate(df, schema, registry)
```

v0.2.0 uses `schema.validate(df, registry)` via `SchemaValidator`:

```python
result = schema.validate(df, registry)
```

**`validate()` still exists** at `nyctea.engine.validate.validate` and has not been removed. It still takes a `FunctionRegistry`. Code calling it directly will continue to work.

But it is not exposed in the top-level `nyctea` namespace and is not the recommended pattern going forward.

**Migration:** use `schema.validate(df, registry)` with a `Registry`.

#### Top-level exports

v0.1.0 exported only `configure_logging` from `nyctea`.

v0.2.0 adds: `SchemaModel`, `Registry`, `FunctionRegistry` (compatibility alias), `register_builtins`, `ValidationResult`, `ValidationReport`, `ErrorReportConfig`, and the exception classes.

This is **additive**. No existing imports break.

---

### What did NOT change

- `SchemaModel`: all fields, methods (`from_dict`, `from_yaml`, `from_yaml_file`, `from_json`, `from_file`), and validators are identical.
- `ValidationResult`, `ValidationReport`, `ErrorReportConfig`: same Pydantic models, same fields.
- Schema YAML/JSON format: schemas written for v0.1.0 load without changes in v0.2.0.
- `ColumnSchema` fields: `dtype`, `nullable`, `required`, `synonyms`, `parsers`, `checks`, `on_failure`.

---

### Upgrade checklist

- [ ] Replace `FunctionRegistry` with `Registry`
- [ ] Replace `validate(df, schema, registry)` with `schema.validate(df, registry)`
- [ ] Call `register_builtins(registry)` to load built-in parsers/checks
- [ ] Re-register custom parsers/checks using `Registry` plugin API (OOP or `ValidatorDecorator` style)
- [ ] Update imports: `from nyctea import Registry, register_builtins`
