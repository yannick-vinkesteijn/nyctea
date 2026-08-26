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

### AggregateEngine

```python
AggregateEngine = Literal["in-memory", "streaming"]
```

The Polars engine used for validation's internal aggregate collects.
Chosen per `validate()` call from `SchemaModel.streaming_row_threshold`, never set directly.
See [streaming engine for internal aggregates](../user-guide/features.md#streaming-engine-for-internal-aggregates).
