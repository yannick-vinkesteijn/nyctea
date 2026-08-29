---
icon: lucide/code
---

# API Reference

Complete reference for Nyctea's public API.

<div class="grid cards" markdown>

-   :lucide-zap:{ .lg .middle } **Validation Engine**

    ---

    `ValidationResult`, `ValidationReport`, `ColumnValidationStats`, `ErrorReportConfig`.

    [:octicons-arrow-right-24: Engine](engine.md)

-   :lucide-layers:{ .lg .middle } **Schema Models**

    ---

    Configuration types from `nyctea.schema`: `ColumnSchema`, `Parser`, `Check`,
    `FrameParser`, `FrameCheck`.

    [:octicons-arrow-right-24: Schema](schema.md)

-   :lucide-plug:{ .lg .middle } **Validator Registry**

    ---

    Extension types from `nyctea.validators`: `ValidatorRegistry`, `ColumnParser`,
    `ColumnCheck`, `FrameParser`, `FrameCheck`.

    [:octicons-arrow-right-24: Registry](registry.md)

-   :lucide-database:{ .lg .middle } **Data Ingestion**

    ---

    Schema-aware readers for CSV and Parquet.

    [:octicons-arrow-right-24: Ingest](ingest.md)

</div>

---

## Public API layers

The root package contains the common workflow:

```python
from nyctea import (
    SchemaModel, Registry, register_builtins, ValidatorDecorator,
    ErrorReportConfig, ValidationReport, ValidationResult,
    NycteaError, PipelineError, ValidationError, ValidatorError,
)
```

Advanced types use explicit namespaces so similarly named schema specifications and
validator classes cannot be confused:

```python
from nyctea.schema import Check, ColumnSchema, FrameCheck, FrameParser, Parser
from nyctea.validators import ColumnCheck, ColumnParser, ValidatorMetadata
from nyctea.engine import ColumnValidationStats
```
