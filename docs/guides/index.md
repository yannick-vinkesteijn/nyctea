---
icon: lucide/book-open
---

# User Guides

Guides for using Nyctea, from first install to custom validators.

!!! tip "New to Nyctea?"

    Start with [Quick Start](quickstart.md) to validate your first DataFrame in under 5 minutes.

---

<div class="grid cards" markdown>

- :material-rocket-launch-outline:{ .lg .middle } **Quick Start**

    ---

    Install Nyctea, define a schema, register validators, and validate your first DataFrame.

    [:octicons-arrow-right-24: Quick Start](quickstart.md)

- :lucide-sparkles:{ .lg .middle } **Features**

    ---

    Overview of lazy validation, error reporting modes, coercion, failure handling, and validators.

    [:octicons-arrow-right-24: Features](features.md)

- :material-puzzle-outline:{ .lg .middle } **Validator Registry**

    ---

    Register custom parsers and checks using OOP classes or the decorator API.

    [:octicons-arrow-right-24: Validator Registry](registry.md)

</div>

---

## What guides cover

| Topic               | Description                                                                |
| ------------------- | -------------------------------------------------------------------------- |
| **Schemas**         | Columns, dtypes, nullability, synonyms, coercion, and failure handling     |
| **Parsers**         | Column-level transformations applied before checks                         |
| **Checks**          | Column-level validation rules (`min_value`, `in_set`, `between`, `unique`) |
| **Registry**        | Registering built-in and custom validators                                    |
| **Pipeline**        | How phases run, how to customise order, how to add your own phase          |
| **Error reporting** | Summary, rows, and cells modes in `ErrorReportConfig`                      |
