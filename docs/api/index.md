# API Reference

Complete API documentation for Nyctea.

## Core Modules

### Validation Engine

The validation engine is the heart of Nyctea, orchestrating the validation pipeline.

::: nyctea.engine.validate.validate

::: nyctea.engine.validate.ValidationResult

::: nyctea.engine.validate.ValidationReport

::: nyctea.engine.validate.ColumnValidationStats

::: nyctea.engine.validate.ErrorReportConfig

### Schema Definition

Define and manage validation schemas.

::: nyctea.schema.model.SchemaModel

::: nyctea.schema.model.ColumnSchema

::: nyctea.schema.model.Parser

::: nyctea.schema.model.Check

::: nyctea.schema.model.ValidationProfile

### Function Registry

Register custom parsers and checks.

::: nyctea.functions.registry.FunctionRegistry

::: nyctea.functions.registry.ColumnFunctionWrapper

::: nyctea.functions.registry.FrameFunctionWrapper

### Data Ingestion

Read data with schema-aware loading.

::: nyctea.ingest.readers.read_csv

::: nyctea.ingest.readers.read_parquet

## Exception Classes

::: nyctea.engine.validate.SchemaResolutionError

::: nyctea.functions.registry.RegistryError

::: nyctea.functions.registry.ColumnPurityError

::: nyctea.functions.registry.FrameShapeError
