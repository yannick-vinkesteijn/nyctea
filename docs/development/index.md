---
icon: lucide/git-branch
---

# Development

Architecture decisions, roadmap, migration notes, and contributor docs.

!!! info "Current version: v0.2.0"
    The plugin system and core pipeline are in place. Several pipeline phases are still stubs. See the [roadmap](roadmap.md) for what's next.

---

<div class="grid cards" markdown>

-   :material-map-outline:{ .lg .middle } **Roadmap**

    ---

    v0.2.0 backlog, planned pipeline phases, and test coverage targets.

    [:octicons-arrow-right-24: Roadmap](roadmap.md)

-   :material-alert-decagram-outline:{ .lg .middle } **Breaking Changes**

    ---

    What changed between v0.1.0 and v0.2.0, and how to migrate.

    [:octicons-arrow-right-24: Breaking Changes](breaking-changes.md)

-   :material-floor-plan:{ .lg .middle } **ADR: Pipeline Design**

    ---

    Why we replaced the monolithic `validate()` function with a composable phase pipeline.

    [:octicons-arrow-right-24: Pipeline ADR](adr-pipeline-design.md)

-   :material-scale-balance:{ .lg .middle } **ADR: Validation API & Library Comparison**

    ---

    Design rationale for `schema.validate(df, registry)`. Comparison with Pandera, Patito, and Dataframely.

    [:octicons-arrow-right-24: API ADR](adr-validation-api.md)

-   :material-tag-outline:{ .lg .middle } **Releasing**

    ---

    How to cut a release: versioning, changelog, and PyPI publish steps.

    [:octicons-arrow-right-24: Releasing](RELEASING.md)

</div>

---

## About this project

Nyctea started as a "vibe code" experiment to explore transferring software engineering knowledge to Claude Code for production Python development. The development history, sprint notes, and lessons learned are documented below.

??? note "Sprint and refactor history"
    - [Sprint 1 Summary](SPRINT_1_COMPLETE.md)
    - [Refactor Summary](REFACTOR_SUMMARY.md)
    - [Type Checking Notes](TYPE_CHECKING_NOTES.md)
    - [Original Refactor Plan](nyctea-refactor-plan.md)
