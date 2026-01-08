# Schema Models

Pydantic models for defining validation schemas.

## SchemaModel

::: nyctea.schema.model.SchemaModel

## ColumnSchema

::: nyctea.schema.model.ColumnSchema

## Parser

::: nyctea.schema.model.Parser

## Check

::: nyctea.schema.model.Check

## FrameParser

::: nyctea.schema.model.FrameParser

## FrameCheck

::: nyctea.schema.model.FrameCheck

## Type Aliases

### ValidationProfile

```python
ValidationProfile = Literal["strict", "clean", "audit"]
```

Defines the available validation profiles:

- `"strict"` - All failures raise errors (default)
- `"clean"` - Nullify failures for nullable columns
- `"audit"` - Like strict, with enhanced reporting

### OnFailureBehavior

```python
OnFailureBehavior = Literal["raise", "null"]
```

Defines how validation failures are handled:

- `"raise"` - Stop validation and report errors
- `"null"` - Set failing values to null and continue
