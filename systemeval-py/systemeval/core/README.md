# SystemEval Core

Framework-agnostic test result structures, evaluation criteria, and unified reporting.

## Schema Hierarchy

```
Adapter.execute() → TestResult → .to_evaluation() → EvaluationResult → JSON
```

1. **TestResult** (`types.py`): Intermediate format returned by adapters
2. **EvaluationResult** (`evaluation.py`): Primary output schema for ALL evaluations

## Modules

| File | Purpose |
|------|---------|
| `evaluation.py` | Unified EvaluationResult schema and factory functions |
| `criteria.py` | Pass/fail criteria library with preset thresholds |
| `reporter.py` | Output formatting (table, JSON, JUnit XML) |

## EvaluationResult Schema

The `EvaluationResult` is the singular contract for all evaluation output:

```python
from systemeval.core import create_evaluation, create_session, metric

# Create evaluation with metadata
evaluation = create_evaluation(
    adapter_type="pytest",
    project_name="my-app",
    category="unit",
)

# Add a session with metrics
session = create_session("test-suite")
session.metrics.append(metric(
    name="tests_passed",
    value=42,
    expected=">0",
    condition=True,
))
evaluation.add_session(session)

# Output
evaluation.finalize()
print(evaluation.to_json())
```

### Structure

```
EvaluationResult
├── metadata (EvaluationMetadata)
│   ├── evaluation_id (UUID)
│   ├── timestamp_utc (ISO 8601)
│   ├── environment (git commit, hostname, python version)
│   ├── adapter_type
│   └── schema_version
├── sessions (List[SessionResult])
│   ├── session_id
│   ├── session_name
│   ├── metrics (List[MetricResult])
│   ├── verdict (computed from metrics)
│   └── artifacts
├── verdict (PASS | FAIL | ERROR)
└── summary (computed statistics)
```

## Criteria Library

Hardcoded pass/fail criteria for common test metrics:

```python
from systemeval.core import (
    TESTS_PASSED,      # At least 1 test passed
    NO_FAILURES,       # Zero test failures
    NO_ERRORS,         # Zero errors (system bugs)
    PASS_RATE_90,      # >= 90% pass rate
    COVERAGE_80,       # >= 80% code coverage
    DURATION_WITHIN_5_MIN,  # Completes within 5 minutes
)

# Create custom criteria
from systemeval.core import pass_rate_minimum, coverage_minimum

MY_PASS_RATE = pass_rate_minimum(95.0)
MY_COVERAGE = coverage_minimum(85.0)
```

### Preset Criteria Sets

| Set | Criteria | Use Case |
|-----|----------|----------|
| `UNIT_TEST_CRITERIA` | tests_passed, no_errors, duration <= 1min | Fast unit tests |
| `INTEGRATION_TEST_CRITERIA` | tests_passed, no_errors, duration <= 5min | Integration tests |
| `E2E_TEST_CRITERIA` | tests_passed, error_rate=0, duration <= 10min | Browser E2E tests |
| `STRICT_CRITERIA` | 100% pass rate, no_errors, coverage >= 80% | CI quality gates |
| `SMOKE_TEST_CRITERIA` | tests_passed, no_errors | Minimal validation |

## Reporter

Unified output formatting with multiple formats:

```python
from systemeval.core import Reporter

reporter = Reporter(
    format="table",    # "table", "json", or "junit"
    verbose=True,      # Show detailed failures
    colors=True,       # Rich console colors
    show_passed=False, # Only show failures
)

reporter.report(evaluation_result)
```

### Output Formats

- **table**: Rich console output with colors
- **json**: Machine-parseable JSON
- **junit**: JUnit XML for CI systems
