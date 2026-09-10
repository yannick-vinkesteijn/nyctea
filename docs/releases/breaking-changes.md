# Breaking Changes

## Within v0.2.0 pre-release: `result.errors` says which kind of failure it is

Every report mode gains a `category` column: `structural` or `check`.

Structural means the data did not meet a precondition: it would not cast, a parser could not read it, or a non-nullable column held a null.
`check` means a rule the schema author wrote was not satisfied.

```
┌────────┬───────────────┬────────────┬───────────┬───────┐
│ column ┆ source_column ┆ category   ┆ check     ┆ count │
╞════════╪═══════════════╪════════════╪═══════════╪═══════╡
│ age    ┆ Age           ┆ structural ┆ coerce    ┆ 1     │
│ age    ┆ Age           ┆ check      ┆ min_value ┆ 1     │
│ age    ┆ Age           ┆ structural ┆ not_null  ┆ 2     │
└────────┴───────────────┴────────────┴───────────┴───────┘
```

Before this, telling the two apart meant knowing that `check in ("coerce", "not_null", "parse")` was the structural set, which was never written down anywhere a user could read.

**Migration:** code reading `result.errors` positionally, or asserting its exact column set, needs updating.
Reading by name is unaffected, and no existing column changed name or meaning.

## Within v0.2.0 pre-release: the error report names the header your file used

`result.errors` gains a `source_column` column in all three report modes.

Column resolution renames a synonym to its canonical name in the first phase, and the mapping used to be built, applied and thrown away.
So once `Age` became `age`, nothing downstream could tell you which column *in your file* failed.

```
┌────────┬───────────────┬───────────┬───────┐
│ column ┆ source_column ┆ check     ┆ count │
╞════════╪═══════════════╪═══════════╪═══════╡
│ age    ┆ Age           ┆ min_value ┆ 1     │
└────────┴───────────────┴───────────┴───────┘
```

`source_column` equals `column` unless the column was matched through a synonym, so the schema is the same shape either way.

The mapping is per-run state and lives on `PipelineContext`, not on `ResolvedColumn`.
A frozen schema is shared across runs and must not know what one particular file called its columns.

**Migration:** code that reads `result.errors` by position, or asserts on its exact column set, needs updating.
Reading by name is unaffected.

## Within v0.2.0 pre-release: run settings moved to `nyctea.Config`

`lazy` and `streaming_row_threshold` describe the machine and the run, not what valid data looks like, so they no longer belong on a schema.
Setting them per schema meant writing them into every schema file and keeping them in sync by hand, and it made batch validation over several schemas unable to share a threshold at all.

`nyctea.Config` mirrors `pl.Config`, so the idiom is one Polars users already know.

```python
import nyctea

nyctea.Config.set_streaming_row_threshold(0)          # globally

with nyctea.Config(lazy=False):                        # scoped to a block
    result = schema.validate(df, registry)

@nyctea.Config(lazy=False)                             # scoped to a function
def run(): ...
```

`save()`, `load()` and `restore_defaults()` work as they do in Polars.

**Migration:** move `lazy` and `streaming_row_threshold` out of your schema files and set them once through `nyctea.Config`.
Both fields still work for one release and still win over the config value when set, but constructing such a schema now emits a `DeprecationWarning`.
Read `schema.resolved_lazy` and `schema.resolved_streaming_row_threshold` for the effective values; `schema.lazy` and `schema.streaming_row_threshold` are now the raw fields and are `None` when unset.

## Within v0.2.0 pre-release: schemas are verified before any data is read

`SchemaModel.verify(registry)` walks every check and parser a schema names, column-level and frame-level, and confirms each against the registry without touching a frame.
`validate()` calls it first, before the data is even converted to a LazyFrame.

A typo used to surface deep in a run, after the rows were loaded:

```
PipelineError: Phase 'column_checks' failed: Check 'posiitve' not found in registry.
```

It now surfaces immediately, with every problem in the schema reported at once rather than one per run:

```
ConfigurationError: Schema does not verify against the registry:
  check 'posiitve' on column 'a' is not registered. Available: between, in_set, min_value, unique
  check 'between' on column 'a' has invalid arguments: Validator 'between' takes (*, min: float, max: float), but got {'min': 0}: missing a required argument: 'max'
  check 'min_value' is declared more than once on column 'a'. Each check name may appear once per column, since the error report is keyed on (column, check).
```

Argument checking is new. It is possible because a validator's keyword-only parameters are now its contract, so arguments bind without running anything.

**Migration:** three failures that used to raise `PipelineError` during a run now raise `ConfigurationError` before it.
An unregistered check or parser name, an unregistered frame check or frame parser, and the same check declared twice on one column.
Catch `ConfigurationError`, exported from `nyctea`, if you were catching `PipelineError` for these.

## Within v0.2.0 pre-release: validators are declared by decorator, not by subclass

`ValidatorDecorator` and the nine built-in validator classes are gone.
Write an expression and decorate it.
The decorators are module-level, so nothing has to be instantiated against a registry first.

```python
import polars as pl
from nyctea import Registry, checker, parser

registry = Registry()

@parser(name="trim", registry=registry)
def trim(column: pl.Expr) -> pl.Expr:
    return column.str.strip_chars()

@checker(name="in_range", registry=registry)
def in_range(column: pl.Expr, *, low: float, high: float) -> pl.Expr:
    return column.is_between(low, high, closed="both")
```

**The signature is the argument contract.**
Keyword-only parameters are what a schema's `args` bind against, so a missing, extra or misspelled argument is reported before any data is read rather than as a failure mid-run.
This replaces the hand-written `validate_args` method every validator used to need.

**Migration.**
`ValidatorDecorator(registry).column_check(name=...)` becomes `@checker(name=..., registry=registry)`, and the same for `parser`, `frame_checker` and `frame_parser`.
Subclasses of `ColumnCheck`, `ColumnParser`, `FrameCheck` and `FrameParser` still work and are still how the decorators are implemented, but they are no longer the documented way to write a validator.
The built-in classes `BetweenCheck`, `InSetCheck`, `MinValueCheck`, `UniqueCheck`, `StripParser`, `ToIntParser`, `ToFloatParser`, `LowerParser` and `UpperParser` were removed.
Their names are unchanged in schemas, so no schema needs editing.

## Within v0.2.0 pre-release: `SchemaValidator` is now `DataValidator`

The class validates data against a schema, but its name said it validated schemas.
Nyctea now uses one verb for each job: data is validated, a schema is verified.
`SchemaModel.verify(registry)` will check that a schema's checks and parsers resolve, and `DataValidator` checks that data conforms.

Plain `Validator` was not available, since it is already the base class of the column and frame validator hierarchy.

Most code never names the class. `SchemaModel.validate(df, registry)` is unchanged and remains the entry point.

**Migration:** rename the import and the constructor call. Nothing else changes.

```python
from nyctea import DataValidator

validator = DataValidator(schema, registry)
result = validator.validate(df)
```

## Within v0.2.0 pre-release: `resolve_column_names` and `SchemaResolutionError` were removed

Both were exported from `nyctea.engine` but no code in the package called them.
`resolve_column_names` was a second implementation of column resolution, superseded by `SchemaModel.resolve_columns` and the `ColumnResolutionPhase` that applies it.
`SchemaResolutionError` existed only to be raised by that function.
Neither was ever marked deprecated, so this is the removal of dead code rather than the end of a deprecation cycle.

The resolution the pipeline actually runs raises `ValidationError` for a missing required column or an ambiguous match.

**Migration:** validate through `SchemaModel.validate()`, which resolves columns as its first phase.
To resolve names without validating, use `SchemaModel.resolve_columns()` and apply the rename yourself.

```python
resolution = schema.resolve_columns(df.collect_schema().names())
if not resolution.is_valid:
    ...  # inspect resolution.missing_required and resolution.ambiguous
df = df.rename(dict(resolution.rename))
```

## Within v0.2.0 pre-release: `SchemaValidator.customize_pipeline()` was removed

The method was a one-line `return self.pipeline.copy()` with a name that promised a customisation API it did not provide.
`DataValidator.pipeline` is a plain attribute, so a copy is available directly.

**Migration:** replace `validator.customize_pipeline()` with `validator.pipeline.copy()`.

```python
pipeline = validator.pipeline.copy()
pipeline.add_phase(MyCustomPhase(), after="column_parsing")
validator.pipeline = pipeline
```

## Within v0.2.0 pre-release: the legacy validation API was removed

Nyctea now has one validation path and one registry. The untested legacy
`nyctea.functions.FunctionRegistry` package, the misleading top-level
`FunctionRegistry` alias, and `nyctea.engine.validate.validate()` were removed.

Use the current API:

```python
import polars as pl

from nyctea import Registry, SchemaModel, ValidatorDecorator

registry = Registry()
decorators = ValidatorDecorator(registry)

@decorators.column_check(name="positive")
def positive(column: pl.Expr) -> pl.Expr:
    return column > 0

schema = SchemaModel.from_dict(...)
result = schema.validate(df, registry)
```

The result models remain importable from `nyctea`; their implementation now lives in
`nyctea.engine.results`. Advanced configuration and extension types use the explicit
`nyctea.schema` and `nyctea.validators` namespaces to avoid name collisions. This
removal also makes the legacy decorator typing defect tracked in #42 obsolete (#43).

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

v0.2.0 introduces the OOP validator system with a clean `Registry` class and removes the earlier `FunctionRegistry` path. The core `SchemaModel` is unchanged.

The documented entry point shifted significantly. If you followed the v0.1.0 README or guides, you will need to update your code.

> **Note:** During pre-release development of v0.2.0, the registry class was temporarily named `MasterRegistry`. The final v0.2.0 release uses `Registry`, which is cleaner and less redundant. If you encountered `MasterRegistry` in any pre-release branch or documentation, replace it with `Registry`.

---

### What changed

The v0.1.0 snippets below are historical examples for migration reference. Their
imports were removed in v0.2.0 and will raise `ModuleNotFoundError` in current
versions; use the corresponding v0.2.0 examples instead.

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

**Migration:** replace `FunctionRegistry` with `Registry`. Re-register custom functions using either OOP validator classes or the `ValidatorDecorator` functional API.

#### Validation entry point

v0.1.0 used the standalone `validate()` function:

```python
from nyctea.engine.validate import validate

result = validate(df, schema, registry)
```

v0.2.0 uses `schema.validate(df, registry)` via `DataValidator`:

```python
result = schema.validate(df, registry)
```

**Migration:** use `schema.validate(df, registry)` with a `Registry`.

#### Top-level exports

v0.1.0 exported only `configure_logging` from `nyctea`.

v0.2.0 adds: `SchemaModel`, `Registry`, `register_builtins`, `ValidationResult`, `ValidationReport`, `ErrorReportConfig`, and the exception classes.

The legacy `FunctionRegistry` and standalone `validate()` imports must be migrated as described above.

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
