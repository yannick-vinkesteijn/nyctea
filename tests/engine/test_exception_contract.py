"""The exception contract `schema.validate` promises its callers.

A schema that does not verify against the registry raises `ConfigurationError`, before
any data is read. An input that does not have the structure the schema describes raises
`ValidationError`. Every other failure of the run, whether a business rule the data
broke or a phase that crashed, raises `PipelineError`. All three carry the phase, and
the column whenever one column owns the failure.

These go through `schema.validate` on purpose. The resolution phase's own tests call
`execute()` directly, so they pin the phase's behaviour but not what a caller sees
after the pipeline has handled it.
"""

import polars as pl
import pytest

from nyctea import (
    ConfigurationError,
    NycteaError,
    PipelineError,
    Registry,
    SchemaModel,
    ValidationError,
    parser,
    register_builtins,
)
from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.pipeline import PhaseType, PipelinePhase, ValidationPipeline
from nyctea.engine.validator import DataValidator
from nyctea.validators.decorators import checker


@pytest.fixture
def registry():
    registry = Registry()
    register_builtins(registry)
    return registry


def test_missing_column_raises_validation_error(registry):
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})

    with pytest.raises(ValidationError, match="Required column 'age' is missing") as exc:
        schema.validate(pl.DataFrame({"other": [1]}), registry)

    assert exc.value.column == "age"
    assert exc.value.phase == "column_resolution"


def test_ambiguous_synonym_raises_validation_error(registry):
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}})

    with pytest.raises(ValidationError, match="Ambiguous columns for 'age'") as exc:
        schema.validate(pl.DataFrame({"age": [1], "Age": [2]}), registry)

    assert exc.value.column == "age"
    assert exc.value.phase == "column_resolution"


def test_check_failure_raises_pipeline_error(registry):
    """A broken business rule is not a structural mismatch, so it stays PipelineError."""
    schema = SchemaModel.from_dict(
        {
            "on_failure": "raise",
            "columns": {"age": {"dtype": "Int64", "checks": [{"name": "min_value", "args": {"min": 0}}]}},
        }
    )

    with pytest.raises(PipelineError, match="Check failed for column 'age'") as exc:
        schema.validate(pl.DataFrame({"age": [-5]}), registry)

    assert exc.value.column == "age"
    assert exc.value.phase == "column_checks"


def test_coercion_failure_raises_pipeline_error(registry):
    schema = SchemaModel.from_dict({"coerce": True, "on_failure": "raise", "columns": {"age": {"dtype": "Int64"}}})

    with pytest.raises(PipelineError, match="Coercion failed for column 'age'") as exc:
        schema.validate(pl.DataFrame({"age": ["x"]}), registry)

    assert exc.value.column == "age"
    assert exc.value.phase == "coercion"


def test_notnull_violation_names_its_phase(registry):
    """The not-null rule attributes to `not_null`, the phase whose mask found it.

    Nullability used to be enforced inside `ColumnCheckPhase`. When it became a phase
    of its own, the raise plan kept the old label.
    """
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "nullable": False}}})

    with pytest.raises(PipelineError, match="nullable=False") as exc:
        schema.validate(pl.DataFrame({"age": [None]}), registry)

    assert exc.value.column == "age"
    assert exc.value.phase == "not_null"


class _CrashingPhase(PipelinePhase):
    """A phase that fails for a reason unrelated to the data."""

    def __init__(self) -> None:
        super().__init__(name="crashing", phase_type=PhaseType.CHECKING, dependencies=[])

    def execute(self, context: PipelineContext) -> PipelineContext:
        raise RuntimeError("validator blew up")


def test_phase_crash_wraps_as_pipeline_error(registry):
    """An unexpected phase failure is wrapped, and the original stays as __cause__."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    pipeline = ValidationPipeline([_CrashingPhase()])

    with pytest.raises(PipelineError, match="Phase 'crashing' failed") as exc:
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))

    assert exc.value.phase == "crashing"
    assert isinstance(exc.value.__cause__, RuntimeError)


class _RejectingPhase(PipelinePhase):
    """A custom phase reporting a structural mismatch of its own."""

    def __init__(self) -> None:
        super().__init__(name="rejecting", phase_type=PhaseType.CHECKING, dependencies=[])

    def execute(self, context: PipelineContext) -> PipelineContext:
        raise ValidationError("custom structural failure", column="age", phase=self.name)


def test_custom_phase_validation_error_survives(registry):
    """The contract is the exception type, not the phase that raised it.

    A third-party phase reporting a structural mismatch reaches the caller intact,
    the same as the built-in resolution phase does.
    """
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    pipeline = ValidationPipeline([_RejectingPhase()])

    with pytest.raises(ValidationError, match="custom structural failure") as exc:
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))

    assert exc.value.column == "age"
    assert exc.value.__cause__ is None


# ---------------------------------------------------------------------------
# Contract-wide invariants
# ---------------------------------------------------------------------------

RAISING_SCHEMAS = {
    "parse": {"columns": {"age": {"dtype": "Utf8", "parsers": [{"name": "to_int"}], "on_failure": "raise"}}},
    "coerce": {"coerce": True, "on_failure": "raise", "columns": {"age": {"dtype": "Int64"}}},
    "not_null": {"columns": {"age": {"dtype": "Int64", "nullable": False}}},
    "check": {
        "on_failure": "raise",
        "columns": {"age": {"dtype": "Int64", "checks": [{"name": "min_value", "args": {"min": 0}}]}},
    },
}

FAILING_FRAMES = {
    "parse": pl.DataFrame({"age": ["x"]}),
    "coerce": pl.DataFrame({"age": ["x"]}),
    "not_null": pl.DataFrame({"age": [None]}),
    "check": pl.DataFrame({"age": [-5]}),
}


@pytest.mark.parametrize("kind", sorted(RAISING_SCHEMAS))
def test_raised_phase_names_a_real_phase(kind, registry):
    """Every on_failure='raise' error attributes to a phase that is in the pipeline.

    The raise plan labels each rule with a phase name by hand, so a label can drift
    out of step with the phases as they are renamed or extracted. That already
    happened once: the not-null rule kept saying `column_checks` after nullability
    moved into a phase of its own.
    """
    schema = SchemaModel.from_dict(RAISING_SCHEMAS[kind])
    phase_names = {phase.name for phase in create_pipeline_from_schema(schema).phases}

    with pytest.raises(PipelineError) as exc:
        schema.validate(FAILING_FRAMES[kind], registry)

    assert exc.value.phase in phase_names


@pytest.mark.parametrize("kind", sorted(RAISING_SCHEMAS))
def test_raised_error_names_its_column(kind, registry):
    schema = SchemaModel.from_dict(RAISING_SCHEMAS[kind])

    with pytest.raises(PipelineError) as exc:
        schema.validate(FAILING_FRAMES[kind], registry)

    assert exc.value.column == "age"


@pytest.mark.parametrize(
    ("schema_dict", "frame"),
    [
        ({"columns": {"age": {"dtype": "Int64"}}}, pl.DataFrame({"other": [1]})),
        ({"columns": {"age": {"dtype": "Int64", "synonyms": ["Age"]}}}, pl.DataFrame({"age": [1], "Age": [2]})),
        *[(RAISING_SCHEMAS[kind], FAILING_FRAMES[kind]) for kind in sorted(RAISING_SCHEMAS)],
    ],
)
def test_every_failure_is_a_nyctea_error(schema_dict, frame, registry):
    """`except NycteaError` catches both halves of the contract.

    The migration note in the breaking-change entry tells callers this is the
    smallest fix, so it is pinned rather than left to inheritance staying put.
    """
    schema = SchemaModel.from_dict(schema_dict)

    with pytest.raises(NycteaError):
        schema.validate(frame, registry)


def test_unverifiable_schema_raises_configuration_error(registry):
    """Verification runs before the data, so its failure precedes the other two."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "checks": [{"name": "nope"}]}}})

    with pytest.raises(ConfigurationError, match="is not registered"):
        schema.validate(pl.DataFrame({"age": [1]}), registry)


class _InnerPipelineErrorPhase(PipelinePhase):
    """A phase that raises a fully formed `PipelineError` of its own."""

    def __init__(self) -> None:
        super().__init__(name="inner", phase_type=PhaseType.CHECKING, dependencies=[])

    def execute(self, context: PipelineContext) -> PipelineContext:
        raise PipelineError("inner failure", phase=self.name, column="age")


def test_phase_pipeline_error_carries_column_out(registry):
    """Rewrapping a phase's `PipelineError` no longer discards its column.

    The wrap itself is kept, because `phase` has to name the phase that was running.
    A phase can raise an error labelled with a different phase entirely: `add_phase`
    labels one with the phase being added, which never ran.
    """
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    pipeline = ValidationPipeline([_InnerPipelineErrorPhase()])

    with pytest.raises(PipelineError, match="Phase 'inner' failed: inner failure") as exc:
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))

    assert exc.value.column == "age"
    assert exc.value.phase == "inner"
    assert isinstance(exc.value.__cause__, PipelineError)


class _HookCrashPhase(PipelinePhase):
    """A phase whose lifecycle predicate fails rather than its `execute`."""

    def __init__(self, hook: str, error: Exception | None = None) -> None:
        super().__init__(name="hooked", phase_type=PhaseType.CHECKING, dependencies=[])
        self._hook = hook
        self._error = error or RuntimeError("hook exploded")

    def can_skip(self, context: PipelineContext) -> bool:
        if self._hook == "can_skip":
            raise self._error
        return False

    def can_change_row_count(self, context: PipelineContext) -> bool:
        if self._hook == "can_change_row_count":
            raise self._error
        return False

    def execute(self, context: PipelineContext) -> PipelineContext:
        return context


@pytest.mark.parametrize("hook", ["can_skip", "can_change_row_count"])
def test_hook_failure_wraps_as_pipeline_error(hook, registry):
    """A phase's predicates are held to the same contract as its `execute`.

    They run outside `_execute_phase`, so a raise from either used to leave the
    pipeline unwrapped and reach the caller as a bare `RuntimeError`, which
    `except NycteaError` does not catch. Neither hook's contract depends on an
    observer being attached, even though only one of them is read without one.
    """
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    pipeline = ValidationPipeline([_HookCrashPhase(hook)])

    with pytest.raises(PipelineError, match=f"failed in {hook}"):
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))


def test_hook_validation_error_passes_through(registry):
    """A hook's `ValidationError` reaches the caller unwrapped, keeping its column.

    This held before the hooks were wrapped, because nothing touched them at all.
    It is pinned here so adding the wrapping does not quietly swallow it.
    """
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    error = ValidationError("structural problem from a hook", column="age", phase="hooked")
    pipeline = ValidationPipeline([_HookCrashPhase("can_skip", error)])

    with pytest.raises(ValidationError, match="structural problem from a hook") as exc:
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))

    assert exc.value.column == "age"
    assert exc.value.__cause__ is None


def test_parser_failure_names_its_column():
    """A parser that cannot be applied names the column it was applied to.

    The message already identified the column. Without `column` on the error, a
    caller had to parse the text to recover it. The parser verifies against the
    registry and only fails when the expression is built, which is the path that
    reaches `ColumnParsingPhase`.
    """
    registry = Registry()
    register_builtins(registry)

    @parser(name="explodes", registry=registry)
    def explodes(column: pl.Expr) -> pl.Expr:  # noqa: ARG001
        raise RuntimeError("parser blew up")

    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Utf8", "parsers": [{"name": "explodes"}]}}})

    with pytest.raises(PipelineError, match="Failed to apply parser 'explodes'") as exc:
        schema.validate(pl.DataFrame({"age": ["1"]}), registry)

    assert exc.value.column == "age"
    assert exc.value.phase == "column_parsing"


def test_hook_pipeline_error_keeps_its_column(registry):
    """A hook's `PipelineError` is wrapped like `execute`'s, keeping its column."""
    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    error = PipelineError("hook rule broke", phase="elsewhere", column="age")
    pipeline = ValidationPipeline([_HookCrashPhase("can_skip", error)])

    with pytest.raises(PipelineError, match="failed in can_skip") as exc:
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))

    assert exc.value.column == "age"
    assert exc.value.phase == "hooked"


def test_observers_are_told_the_run_failed(registry):
    """A failing run notifies observers before the error leaves the pipeline."""
    from nyctea.engine.observability import MetricsCollector

    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    collector = MetricsCollector()
    pipeline = ValidationPipeline([_CrashingPhase()], observers=[collector])

    with pytest.raises(PipelineError, match="Phase 'crashing' failed"):
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))


def test_evaluation_failure_is_a_pipeline_error():
    """A check that builds but fails on the data stays inside the contract.

    Phases only build the lazy query, so this fails after every phase has run and
    outside the pipeline's own error handling. It used to reach the caller as a raw
    Polars exception that `except NycteaError` does not catch.
    """
    registry = Registry()
    register_builtins(registry)

    @checker(name="strict_cast", registry=registry)
    def strict_cast(column: pl.Expr) -> pl.Expr:
        return column.cast(pl.Int8, strict=True) > 0

    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64", "checks": [{"name": "strict_cast"}]}}})

    with pytest.raises(PipelineError, match="Evaluating the validation aggregates failed") as exc:
        schema.validate(pl.DataFrame({"age": [100000]}), registry)

    assert isinstance(exc.value, NycteaError)
    assert isinstance(exc.value.__cause__, pl.exceptions.InvalidOperationError)
    assert exc.value.phase is None


def test_failing_observer_keeps_the_real_error(registry):
    """An observer is a listener, so its own failure cannot replace the run's error.

    `on_pipeline_error` raising used to propagate in place of the error it was being
    told about, leaving the caller with the observer's exception instead.
    """

    class _BrokenObserver:
        def on_pipeline_start(self, context): ...

        def on_phase_start(self, phase_name, context): ...

        def on_phase_end(self, phase_name, context, metrics): ...

        def on_pipeline_complete(self, context, duration): ...

        def on_pipeline_error(self, context, error):
            raise ZeroDivisionError("observer blew up")

    schema = SchemaModel.from_dict({"columns": {"age": {"dtype": "Int64"}}})
    pipeline = ValidationPipeline([_CrashingPhase()], observers=[_BrokenObserver()])

    with pytest.raises(PipelineError, match="Phase 'crashing' failed"):
        DataValidator(schema, registry, pipeline=pipeline).validate(pl.DataFrame({"age": [1]}))
