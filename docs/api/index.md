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

    `SchemaModel`, `ColumnSchema`, `Parser`, `Check`, `ValidationProfile`.

    [:octicons-arrow-right-24: Schema](schema.md)

-   :lucide-plug:{ .lg .middle } **Plugin Registry**

    ---

    `Registry`, `PluginRegistry`, `ColumnParser`, `ColumnCheck`, `FrameParser`, `FrameCheck`.

    [:octicons-arrow-right-24: Registry](registry.md)

-   :lucide-database:{ .lg .middle } **Data Ingestion**

    ---

    Schema-aware readers for CSV and Parquet.

    [:octicons-arrow-right-24: Ingest](ingest.md)

</div>

---

## Public exports

Everything importable directly from `nyctea`:

```python
from nyctea import (
    SchemaModel,          # schema definition
    Registry,       # plugin registry
    register_builtins,    # register built-in parsers/checks
    ValidationResult,     # result of a validation run
    ValidationReport,     # per-column statistics
    ErrorReportConfig,    # error reporting mode (summary/rows/cells)
    NycteaError,          # base exception
    ValidationError,      # column/pipeline validation failure
    ValidatorError,          # plugin registration or execution failure
    PipelineError,        # pipeline phase failure
)
```
