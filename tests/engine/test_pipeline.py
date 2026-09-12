"""Tests for validation pipeline."""

import polars as pl
import pytest

from nyctea.engine.context import PipelineContext
from nyctea.engine.factory import create_pipeline_from_schema
from nyctea.engine.observability import MetricsCollector
from nyctea.engine.phases import ColumnResolutionPhase, FrameParsingPhase
from nyctea.engine.pipeline import PhaseType, PipelinePhase, ValidationPipeline
from nyctea.exceptions import PipelineError
from nyctea.schema.model import SchemaModel
from nyctea.validators.decorators import frame_parser
from nyctea.validators.registry import Registry


class SimplePhase(PipelinePhase):
    """Simple phase for testing."""

    def __init__(self, name="simple", dependencies=None, pinned=None):
        """Initialize the test phase."""
        super().__init__(name=name, phase_type=PhaseType.CHECKING, dependencies=dependencies or [], pinned=pinned)
        self.executed = False

    def execute(self, context: PipelineContext) -> PipelineContext:
        self.executed = True
        return context


def test_pipeline_phase_creation():
    """Test creating a pipeline phase."""
    phase = SimplePhase(name="test")
    assert phase.name == "test"
    assert phase.phase_type == PhaseType.CHECKING
    assert phase.dependencies == []


def test_pipeline_phase_can_skip_default():
    """Test that phases don't skip by default."""
    phase = SimplePhase()
    context = PipelineContext(
        data=pl.LazyFrame(),
        schema=SchemaModel(columns={}),
        registry=Registry(),
    )
    assert phase.can_skip(context) is False


def test_validation_pipeline_creation():
    """Test creating a validation pipeline."""
    pipeline = ValidationPipeline()
    assert len(pipeline) == 0


def test_validation_pipeline_with_phases():
    """Test creating pipeline with initial phases."""
    phases = [SimplePhase(name="p1"), SimplePhase(name="p2")]
    pipeline = ValidationPipeline(phases=phases)
    assert len(pipeline) == 2


def test_pipeline_add_phase():
    """Test adding a phase to pipeline."""
    pipeline = ValidationPipeline()
    phase = SimplePhase(name="test")

    pipeline.add_phase(phase)
    assert len(pipeline) == 1
    assert "test" in pipeline.list_phases()


def test_pipeline_add_phase_after():
    """Test adding a phase after another."""
    pipeline = ValidationPipeline()
    phase1 = SimplePhase(name="first")
    phase2 = SimplePhase(name="second")

    pipeline.add_phase(phase1)
    pipeline.add_phase(phase2, after="first")

    phases = pipeline.list_phases()
    assert phases == ["first", "second"]


def test_pipeline_add_phase_before():
    """Test adding a phase before another."""
    pipeline = ValidationPipeline()
    phase1 = SimplePhase(name="first")
    phase2 = SimplePhase(name="second")
    pipeline.add_phase(phase2)

    pipeline.add_phase(phase1, before="second")

    assert pipeline.list_phases() == ["first", "second"]


def test_pipeline_remove_phase():
    """Test removing a phase from pipeline."""
    pipeline = ValidationPipeline()
    phase = SimplePhase(name="test")

    pipeline.add_phase(phase)
    assert len(pipeline) == 1

    pipeline.remove_phase("test")
    assert len(pipeline) == 0


def test_pipeline_cannot_remove_required_phase():
    """Test that phases with dependents cannot be removed."""
    pipeline = ValidationPipeline()
    phase1 = SimplePhase(name="base")
    phase2 = SimplePhase(name="dependent", dependencies=["base"])

    pipeline.add_phase(phase1)
    pipeline.add_phase(phase2)

    with pytest.raises(PipelineError, match="required by"):
        pipeline.remove_phase("base")


def test_pipeline_dependency_validation():
    """Test that missing dependencies are detected."""
    phase = SimplePhase(name="test", dependencies=["missing"])

    with pytest.raises(PipelineError, match="not in the pipeline"):
        ValidationPipeline(phases=[phase])


def test_pipeline_dependency_ordering():
    """Test that dependencies must come before dependents."""
    phase1 = SimplePhase(name="second", dependencies=["first"])
    phase2 = SimplePhase(name="first")

    # This should fail because dependent comes before dependency
    with pytest.raises(PipelineError, match="Dependencies must run before"):
        ValidationPipeline(phases=[phase1, phase2])


# ---------------------------------------------------------------------------
# Pinned phases: a structural position, independent of `dependencies`.
# ---------------------------------------------------------------------------


def test_pinned_rejects_invalid_value():
    """An invalid value must raise, not silently behave as unpinned."""
    with pytest.raises(PipelineError, match="pinned='middle'"):
        SimplePhase(name="a", pinned="middle")


def test_pinned_first_phase_at_start():
    pipeline = ValidationPipeline(phases=[SimplePhase(name="a", pinned="first"), SimplePhase(name="b")])
    assert pipeline.list_phases() == ["a", "b"]


def test_pinned_first_phase_wrong_position():
    with pytest.raises(PipelineError, match="'a' is pinned first, but is at position 1"):
        ValidationPipeline(phases=[SimplePhase(name="b"), SimplePhase(name="a", pinned="first")])


def test_pinned_last_phase_at_end():
    pipeline = ValidationPipeline(phases=[SimplePhase(name="a"), SimplePhase(name="b", pinned="last")])
    assert pipeline.list_phases() == ["a", "b"]


def test_pinned_last_phase_wrong_position():
    with pytest.raises(PipelineError, match="'b' is pinned last, but is at position 0"):
        ValidationPipeline(phases=[SimplePhase(name="b", pinned="last"), SimplePhase(name="a")])


def test_add_phase_after_pinned_last_rejected():
    pipeline = ValidationPipeline(phases=[SimplePhase(name="a"), SimplePhase(name="last", pinned="last")])

    with pytest.raises(PipelineError, match="'last' is pinned last"):
        pipeline.add_phase(SimplePhase(name="c"), after="last")

    assert pipeline.list_phases() == ["a", "last"], "the rejected insertion must roll back"


def test_add_phase_before_pinned_first_rejected():
    pipeline = ValidationPipeline(phases=[SimplePhase(name="first", pinned="first"), SimplePhase(name="a")])

    with pytest.raises(PipelineError, match="'first' is pinned first"):
        pipeline.add_phase(SimplePhase(name="c"), before="first")

    assert pipeline.list_phases() == ["first", "a"], "the rejected insertion must roll back"


def test_unpinned_phases_reorder_freely():
    """Two phases with no dependency on each other are valid in either order."""
    forward = ValidationPipeline(phases=[SimplePhase(name="a"), SimplePhase(name="b")])
    reverse = ValidationPipeline(phases=[SimplePhase(name="b"), SimplePhase(name="a")])
    assert forward.list_phases() == ["a", "b"]
    assert reverse.list_phases() == ["b", "a"]


def test_pipeline_list_phases():
    """Test listing phase names."""
    pipeline = ValidationPipeline()
    pipeline.add_phase(SimplePhase(name="a"))
    pipeline.add_phase(SimplePhase(name="b"))

    phases = pipeline.list_phases()
    assert phases == ["a", "b"]


def test_pipeline_repr():
    """Test pipeline repr."""
    pipeline = ValidationPipeline()
    pipeline.add_phase(SimplePhase())

    repr_str = repr(pipeline)
    assert "ValidationPipeline" in repr_str
    assert "1 phases" in repr_str


def _context_with_row_index():
    lf = pl.LazyFrame({"a": [1, 2, 3]}).with_row_index("__row_index__")
    return PipelineContext(data=lf, schema=SchemaModel(columns={}), registry=Registry())


def test_metrics_skipped_without_observers(collect_calls):
    """The per-phase metrics block must not collect when nothing observes it."""
    pipeline = ValidationPipeline(phases=[SimplePhase(name="p1")])
    pipeline.execute(_context_with_row_index())

    assert len(collect_calls) == 0


def test_execute_phase_collects_metrics_with_observers():
    """The observer path still gets real metrics once the metrics block is guarded."""
    collector = MetricsCollector()
    pipeline = ValidationPipeline(phases=[SimplePhase(name="p1")], observers=[collector])
    pipeline.execute(_context_with_row_index())

    assert len(collector.phase_metrics) == 1
    assert collector.phase_metrics[0].phase_name == "p1"
    assert collector.phase_metrics[0].rows_processed == 3


def test_metrics_zero_rows_without_row_index():
    """A context built without row tracking still runs; the initial count is 0."""
    collector = MetricsCollector()
    context = PipelineContext(data=pl.LazyFrame({"a": [1, 2, 3]}), schema=SchemaModel(columns={}), registry=Registry())
    pipeline = ValidationPipeline(phases=[SimplePhase(name="p1")], observers=[collector])

    pipeline.execute(context)

    assert collector.phase_metrics[0].rows_processed == 0


def test_metrics_follow_frame_row_changes():
    registry = Registry()

    @frame_parser(registry=registry, name="keep_first")
    def keep_first(frame: pl.LazyFrame) -> pl.LazyFrame:
        return frame.head(1)

    schema = SchemaModel.from_dict(
        {
            "frame_parsers": [{"name": "keep_first"}],
            "columns": {"a": {"dtype": "Int64", "nullable": True}},
        }
    )
    context = PipelineContext(
        data=pl.LazyFrame({"a": [1, 2, 3]}).with_row_index("__row_index__"),
        schema=schema,
        registry=registry,
    )
    collector = MetricsCollector()

    create_pipeline_from_schema(schema, observers=[collector]).execute(context)

    rows_by_phase = {metric.phase_name: metric.rows_processed for metric in collector.phase_metrics}
    assert rows_by_phase["frame_parsing"] == 3
    assert rows_by_phase["coercion"] == 1


def test_skipped_row_phase_does_not_recount(collect_calls):
    collector = MetricsCollector()
    pipeline = ValidationPipeline(
        phases=[ColumnResolutionPhase(), FrameParsingPhase(), SimplePhase()],
        observers=[collector],
    )

    pipeline.execute(_context_with_row_index())

    assert len(collect_calls) == 1


# ---------------------------------------------------------------------------
# Pipeline mutation API (#68 coverage)
#
# Every path below is public and had no test behind it. `copy()` in particular
# is a public method nothing in the package calls.
# ---------------------------------------------------------------------------


def test_phase_repr_names_the_phase():
    assert repr(SimplePhase(name="p1")) == "SimplePhase(name='p1')"


def test_copy_shares_no_phase_list():
    """A copy can be reordered without disturbing the pipeline it came from."""
    original = ValidationPipeline(phases=[SimplePhase(name="p1")], observers=[MetricsCollector()])

    duplicate = original.copy()
    duplicate.add_phase(SimplePhase(name="p2"))

    assert [p.name for p in original.phases] == ["p1"]
    assert [p.name for p in duplicate.phases] == ["p1", "p2"]
    assert duplicate.observers == original.observers


def test_add_phase_rejects_after_and_before():
    pipeline = ValidationPipeline(phases=[SimplePhase(name="p1")])

    with pytest.raises(ValueError, match="Cannot specify both 'after' and 'before'"):
        pipeline.add_phase(SimplePhase(name="p2"), after="p1", before="p1")


@pytest.mark.parametrize("position", ["after", "before"])
def test_add_phase_rejects_unknown_neighbour(position):
    """Naming a phase that is not in the pipeline fails instead of appending silently."""
    pipeline = ValidationPipeline(phases=[SimplePhase(name="p1")])

    with pytest.raises(PipelineError, match=f"{position} 'nope': phase 'nope' not found"):
        pipeline.add_phase(SimplePhase(name="p2"), **{position: "nope"})

    assert [p.name for p in pipeline.phases] == ["p1"]


class _MutatingPhase(PipelinePhase):
    """A phase that tries to reshape the pipeline it is running inside."""

    def __init__(self, pipeline_ref: dict, action: str) -> None:
        super().__init__(name="mutating", phase_type=PhaseType.CHECKING, dependencies=[])
        self._pipeline_ref = pipeline_ref
        self._action = action

    def execute(self, context: PipelineContext) -> PipelineContext:
        pipeline = self._pipeline_ref["pipeline"]
        if self._action == "add":
            pipeline.add_phase(SimplePhase(name="late"))
        else:
            pipeline.remove_phase("mutating")
        return context


@pytest.mark.parametrize("action", ["add", "remove"])
def test_pipeline_locked_during_execution(action):
    """The phase list is frozen for the duration of a run.

    Reshaping it mid-run would leave the loop iterating a list that no longer
    matches the ordering the pipeline validated before it started.
    """
    ref = {}
    pipeline = ValidationPipeline(phases=[_MutatingPhase(ref, action)])
    ref["pipeline"] = pipeline

    with pytest.raises(PipelineError, match="Cannot modify pipeline after validation has started"):
        pipeline.execute(_context_with_row_index())
