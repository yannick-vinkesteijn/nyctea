# Data Ingestion

Schema-aware data reading functions.

## CSV Reading

### read_csv

::: nyctea.ingest.readers.read_csv

## Parquet Reading

### read_parquet

::: nyctea.ingest.readers.read_parquet

## Usage Examples

### Reading CSV with String Types (Recommended)

This is the recommended approach for validation workflows:

```python
from nyctea.ingest import read_csv
from nyctea.schema.model import SchemaModel

schema = SchemaModel.from_yaml_file("schema.yaml")

# All columns read as strings
lf = read_csv("data.csv", schema, lazy=True)
```

This prevents Polars from inferring types, giving Nyctea full control over type coercion and error handling.

### Reading CSV with Declared Types

Use this when you want Polars to directly cast to the schema dtypes (like Pandera/Patito):

```python
# Polars will cast columns during read
lf = read_csv("data.csv", schema, lazy=True, typed=True)
```

### Handling Synonyms

The readers automatically match physical column names using canonical names and synonyms:

```python
# Schema defines:
# canonical: "passenger_id"
# synonym: "PassengerId"

# CSV has column "PassengerId"
lf = read_csv("titanic.csv", schema, lazy=True)
# Column is automatically matched!
```

### Lazy vs Eager

Control whether to return a LazyFrame or DataFrame:

```python
# LazyFrame (recommended for large data)
lf = read_csv("data.csv", schema, lazy=True)

# DataFrame (eager evaluation)
df = read_csv("data.csv", schema, lazy=False)

# Use schema default
lf_or_df = read_csv("data.csv", schema)  # Uses schema.lazy
```

## Advanced Usage

### Multiple Files

```python
from nyctea.ingest import read_parquet

# Read multiple Parquet files
lf = read_parquet(["part1.parquet", "part2.parquet"], schema, lazy=True)
```

### Custom Schema Overrides

For advanced use cases, you can access the schema override dict:

```python
import polars as pl
from nyctea.schema.model import SchemaModel

schema = SchemaModel.from_yaml_file("schema.yaml")

# Build custom overrides
schema_overrides = {}
for name, col_schema in schema.columns.items():
    schema_overrides[name] = pl.Utf8
    for synonym in col_schema.synonyms:
        schema_overrides[synonym] = pl.Utf8

# Use directly with Polars
lf = pl.scan_csv("data.csv", schema_overrides=schema_overrides)
```
