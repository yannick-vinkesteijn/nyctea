# Breaking Changes

## Within v0.2.0 pre-release: duplicate check names on one column now raise

A column could declare two checks with the same name, most plausibly the same parameterised check
with different arguments:

```python
"checks": [
    {"name": "between", "args": {"min": 0, "max": 5}},
    {"name": "between", "args": {"min": 0, "max": 100}},
]
```

This never worked. `check_masks`, `result.errors`, and the per-column report stats are all keyed
on `(column, check name)`, so the second declaration overwrote the first and orphaned its mask.
The first check was dropped from reporting *and* from enforcement: in the example above, value
`30` violates the declared `between(0, 5)` under the default `on_failure: "raise"`, and validation
returned no errors, raised nothing, and reported `2/2 rows valid (100.0%)`.

Nyctea now raises `PipelineError` when a column declares the same check name twice.

**Migration:** give the checks distinct names. Register the second under its own name rather than
reusing the first, or express the intent as a single check. A schema that hits this error was
already producing wrong results, so no working configuration is affected.

Note that the same check name on *different* columns was always fine and remains so; the key is
the pair, not the name alone.

## Within v0.2.0 pre-release: `nullable: false` is now enforced

`ColumnSchema.nullable` defaults to `false`. Until now the not-null constraint was never applied,
so nulls passed validation in every column that did not declare `nullable: true`. That gap is
closed. A column that does not say `nullable: true` now fails validation when it contains a null.

This is a behavior change, not only a bug fix. Schemas that relied on the previous silence will
start raising.

**Migration:** add `nullable: true` to every column that legitimately contains nulls. Columns that
should reject nulls need no change; they are now enforced as always intended.

Failure handling follows the column's resolved `on_failure`:

| `on_failure` | Behavior on a null in a `nullable: false` column |
| --- | --- |
| `raise` (default) | Raises `PipelineError` |
| `ignore` | Passes the value through and reports it in `errors` under check name `not_null` |

Note that `on_failure: "null"` cannot apply here. `SchemaModel.resolve_on_failure` downgrades it
to `raise` for any non-nullable column, and since `nullable` defaults to `false` that covers most
columns. This silent downgrade is tracked separately; it should become a schema validation error
rather than a substitution.

## Within v0.2.0 pre-release: `plugins` → `validators`

Before the first public release, the extensibility system was renamed from "plugin" to "validator" terminology, to match the existing `Validator`/`ValidatorMetadata` base classes and avoid confusion with unrelated plugin-based projects.

| Old (pre-release) | New |
| --- | --- |
| `nyctea.plugins` (module) | `nyctea.validators` |
| `ColumnPlugin` | `ColumnValidator` |
| `FramePlugin` | `FrameValidator` |
| `PluginRegistry` | `ValidatorRegistry` |
| `RegistrationError(plugin_name=..., plugin_type=...)` | `RegistrationError(validator_name=..., validator_type=...)` |
| `ValidatorExecutionError(plugin_name=..., plugin_type=...)` | `ValidatorExecutionError(validator_name=..., validator_type=...)` |

`ColumnParser`, `ColumnCheck`, `FrameParser`, `FrameCheck`, `Registry`, `ValidatorMetadata`, and `ValidatorDecorator` are unchanged, they never used "plugin" in their names.

**Migration:** update any `from nyctea.plugins...` import to `from nyctea.validators...`, and rename `ColumnPlugin`/`FramePlugin`/`PluginRegistry` usages to their `*Validator` equivalents.

## v0.1.0 → v0.2.0

### Summary

v0.2.0 introduces the OOP validator system with a clean `Registry` class alongside the existing `FunctionRegistry`. The core `SchemaModel` is unchanged. No public API symbols that were exported in v0.1.0 have been removed.

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

v0.2.0 introduces `Registry` with OOP validator classes and a `register_builtins()` shortcut:

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

**Migration:** replace `FunctionRegistry` with `Registry`. Re-register custom functions using either OOP validator classes or the `ValidatorDecorator` functional API.

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
- [ ] Re-register custom parsers/checks using `Registry` validator API (OOP or `ValidatorDecorator` style)
- [ ] Update imports: `from nyctea import Registry, register_builtins`
