# Nyctea Test Suite

## Running Tests

### Run all tests

```bash
uv run pytest tests/ -v
```

### Run with coverage

```bash
uv run pytest tests/ --cov=src/nyctea --cov-report=term --cov-report=html
```

### Run specific test file

```bash
uv run pytest tests/test_validation_minimal.py -v
```

### Run specific test

```bash
uv run pytest tests/test_validation_minimal.py::test_parsers_applied_correctly -v
```

## Current Test Coverage

**Status:** ✅ 8 tests passing (48% coverage)

### Test Files

- **test_validation_minimal.py** - Core validation functionality tests
  - Schema loading
  - Plugin registry
  - Parser application
  - Check execution
  - Validation reports
  - Error handling

## Coverage by Module

| Module                        | Coverage | Notes                     |
| ----------------------------- | -------- | ------------------------- |
| `__init__.py`                 | 100%     | Main exports              |
| `schema/validator.py`         | 95%      | SchemaValidator           |
| `plugins/builtins/parsers.py` | 84%      | Built-in parsers          |
| `plugins/registry.py`         | 81%      | Plugin registration       |
| `engine/phases.py`            | 83%      | Pipeline phases           |
| `engine/pipeline.py`          | 59%      | Pipeline orchestration    |
| `engine/validate.py`          | 14%      | Legacy (to be deprecated) |

## Adding New Tests

### Test Structure

```python
import pytest
from nyctea import SchemaModel, MasterRegistry, register_builtins

@pytest.fixture
def registry():
    reg = MasterRegistry()
    register_builtins(reg)
    return reg

def test_my_feature(registry):
    # Your test code
    assert True
```

### Running Tests in CI

Tests run automatically on:

- Every push to `main`
- Every pull request
- Multiple Python versions (3.10, 3.11, 3.12)

See `.github/workflows/ci.yml` for CI configuration.

## Future Test Additions (Sprint 2+)

- [ ] Frame parser tests
- [ ] Frame check tests
- [ ] Error reporting tests (rows/cells mode)
- [ ] Pipeline customization tests
- [ ] Observability tests (logging, metrics)
- [ ] Plugin validation tests (purity, shape)
- [ ] Integration tests with Titanic example
- [ ] Performance benchmarks
