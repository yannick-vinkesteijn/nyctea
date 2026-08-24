---
icon: lucide/git-branch
---

# Development

Architecture decisions, migration notes, and contributor docs.

!!! info "Current version: v0.2.0"
    The validator system and core pipeline are in place. See the [open issues](https://github.com/yannick-vinkesteijn/nyctea/issues) for what's next.

---

<div class="grid cards" markdown>

-   :material-source-pull:{ .lg .middle } **Contributing**

    ---

    Issue-first workflow, branch and PR conventions, local dev setup, CI overview.

    [:octicons-arrow-right-24: Contributing](contributing.md)

-   :material-alert-decagram-outline:{ .lg .middle } **Breaking Changes**

    ---

    What changed between v0.1.0 and v0.2.0, and how to migrate.

    [:octicons-arrow-right-24: Breaking Changes](../releases/breaking-changes.md)

-   :material-floor-plan:{ .lg .middle } **ADR: Pipeline Design**

    ---

    Why we replaced the monolithic `validate()` function with a composable phase pipeline.

    [:octicons-arrow-right-24: Pipeline ADR](decisions/adr-pipeline-design.md)

-   :material-scale-balance:{ .lg .middle } **ADR: Validation API & Library Comparison**

    ---

    Design rationale for `schema.validate(df, registry)`. Comparison with Pandera, Patito, and Dataframely.

    [:octicons-arrow-right-24: API ADR](decisions/adr-validation-api.md)

-   :material-tag-outline:{ .lg .middle } **Releasing**

    ---

    How to cut a release: versioning, changelog, and PyPI publish steps.

    [:octicons-arrow-right-24: Releasing](RELEASING.md)

</div>

---

## About this project

Nyctea is a Polars-native validation library. This section holds contributor documentation: how to contribute, the release process, and architecture decisions. Work is tracked as [GitHub issues](https://github.com/yannick-vinkesteijn/nyctea/issues), not a roadmap page.
