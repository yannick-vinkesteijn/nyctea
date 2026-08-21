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

### OnFailureBehavior

```python
OnFailureBehavior = Literal["raise", "null", "ignore"]
```

Controls what happens when coercion or checks fail. Set at schema level (default for all columns) or per column (override).

- `"raise"` - Error, stop. Default.
- `"null"` - Value becomes null. Requires `nullable=True`.
- `"ignore"` - Coercion nulls forced by dtype. Check failures kept as-is, reported.
