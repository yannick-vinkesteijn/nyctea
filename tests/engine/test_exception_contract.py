"""The exception contract `schema.validate` promises its callers.

A structural mismatch between schema and data raises `ValidationError`. Every other
failure, whether a business rule the data broke or a phase that crashed, raises
`PipelineError`. Both carry the column and phase that produced them.

These go through `schema.validate` on purpose. The resolution phase's own tests call
`execute()` directly, so they pin the phase's behaviour but not what a caller sees
after the pipeline has handled it.
"""

import polars as pl
import pytest

from nyctea import NycteaError, PipelineError, Registry, SchemaModel, ValidationError, register_builtins
from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.pipeline import PhaseType, PipelinePhase, ValidationPipeline
from nyctea.engine.validator import DataValidator


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

    `NotNullPhase` became a phase of its own in #87. The raise plan kept labelling its
    failures `column_checks`, which is where nullability used to be enforced.
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
    happened once: the not-null rule kept saying `column_checks` after #87 moved
    nullability into a phase of its own.
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
