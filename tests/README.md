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
    - Validator registry
    - Parser application
    - Check execution
    - Validation reports
    - Error handling

## Coverage by Module

| Module                           | Coverage | Notes                  |
| -------------------------------- | -------- | ---------------------- |
| `__init__.py`                    | 100%     | Main exports           |
| `engine/validator.py`            | 95%      | DataValidator          |
| `validators/builtins/parsers.py` | 84%      | Built-in parsers       |
| `validators/registry.py`         | 81%      | Validator registration |
| `engine/phases.py`               | 83%      | Pipeline phases        |
| `engine/pipeline.py`             | 59%      | Pipeline orchestration |

## Adding New Tests

### Test Structure

```python
import pytest
from nyctea import SchemaModel, Registry, register_builtins


@pytest.fixture
def registry():
    reg = Registry()
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
- Multiple Python versions (3.11, 3.12, 3.13, 3.14)

See `.github/workflows/ci.yml` for CI configuration.

## Future Test Additions (Sprint 2+)

- [ ] Frame parser tests
- [ ] Frame check tests
- [ ] Error reporting tests (rows/cells mode)
- [ ] Pipeline customization tests
- [ ] Observability tests (logging, metrics)
- [ ] Validator tests (purity, shape)
- [ ] Integration tests with Titanic example
- [ ] Performance benchmarks
