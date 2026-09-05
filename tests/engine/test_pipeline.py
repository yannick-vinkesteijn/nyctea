"""Tests for validation pipeline."""

import polars as pl
import pytest

from nyctea.engine.context import PipelineContext
from nyctea.engine.observability import MetricsCollector
from nyctea.engine.pipeline import PhaseType, PipelinePhase, ValidationPipeline
from nyctea.exceptions import PipelineError
from nyctea.schema.model import SchemaModel
from nyctea.validators.registry import Registry


class SimplePhase(PipelinePhase):
    """Simple phase for testing."""

    def __init__(self, name="simple", dependencies=None):
        """Initialize the test phase."""
        super().__init__(name=name, phase_type=PhaseType.CHECKING, dependencies=dependencies or [])
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
    """#11 step 1: the per-phase metrics block must not collect when nothing observes it."""
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
