# SystemEval Schema Hierarchy

## Overview

This document clarifies the relationship between the three result schemas in SystemEval and establishes the canonical flow for test evaluation output.

## The Problem (Before)

Three competing result schemas existed:

1. `adapters/base.py` - **TestResult** dataclass
2. `core/evaluation.py` - **EvaluationResult** with full schema
3. `core/result.py` - **SequenceResult** (legacy)

This created confusion about which schema to use and when.

## The Solution (After)

### Schema Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                    SCHEMA ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. TestResult (adapters/base.py)                              │
│     ├─ Role: INTERMEDIATE format                               │
│     ├─ Returned by: adapter.execute()                          │
│     ├─ Contains: passed, failed, errors, skipped, duration     │
│     └─ Purpose: Raw test execution counts                      │
│                                                                 │
│                         │                                       │
│                         │ .to_evaluation()                     │
│                         ▼                                       │
│                                                                 │
│  2. EvaluationResult (core/evaluation.py)                      │
│     ├─ Role: PRIMARY output schema                             │
│     ├─ Returned by: TestResult.to_evaluation()                 │
│     ├─ Contains: metadata, sessions, verdict, summary          │
│     └─ Purpose: Complete evaluation report with context        │
│                                                                 │
│                         │                                       │
│                         │ .to_json()                           │
│                         ▼                                       │
│                                                                 │
│  3. JSON Output                                                │
│     └─ Final serialized evaluation result                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Deprecated Schema (DO NOT USE)

- **`core/result.py`**: Contains legacy `SequenceResult`, `SessionResult`, `MetricResult`
  - Only kept for backward compatibility
  - Has naming conflicts with evaluation.py classes
  - Will be removed in future versions
  - Emits deprecation warnings when used

## Canonical Flow

```python
# 1. Adapter discovers tests
tests = adapter.discover(category="unit")

# 2. Adapter executes tests → TestResult
result = adapter.execute(tests)  # Returns TestResult

# 3. Convert to unified EvaluationResult
evaluation = result.to_evaluation(
    adapter_type="pytest",
    project_name="my-project"
)

# 4. Finalize (computes hash, duration, verdict)
evaluation.finalize()

# 5. Output as JSON
print(evaluation.to_json())
```

## Never Skip the Conversion

**WRONG:**
```python
result = adapter.execute(tests)
# ERROR: TestResult doesn't have .to_json()
print(result.to_json())  # This will fail!
```

**CORRECT:**
```python
result = adapter.execute(tests)
evaluation = result.to_evaluation(adapter_type="pytest")
evaluation.finalize()
print(evaluation.to_json())  # Works!
```

## Schema Responsibilities

### TestResult (Intermediate)

**Location:** `systemeval/adapters/base.py`

**Purpose:** Simple data container for test execution counts

**Fields:**
- `passed: int` - Number of passed tests
- `failed: int` - Number of failed tests
- `errors: int` - Number of error tests
- `skipped: int` - Number of skipped tests
- `duration: float` - Total execution time
- `exit_code: int` - Process exit code
- `coverage_percent: Optional[float]` - Code coverage
- `failures: List[TestFailure]` - Detailed failure information

**Methods:**
- `.verdict` - Property that computes PASS/FAIL/ERROR
- `.to_dict()` - Convert to dictionary
- `.to_evaluation()` - Convert to EvaluationResult (PRIMARY method)

**When to use:** Only returned by adapter.execute(). Never use directly for output.

### EvaluationResult (Final)

**Location:** `systemeval/core/evaluation.py`

**Purpose:** Complete evaluation report with metadata, sessions, and verdicts

**Fields:**
- `metadata: EvaluationMetadata` - Unique ID, timestamps, environment
- `sessions: List[SessionResult]` - Individual test sessions
- `diagnostics: List[str]` - Diagnostic messages
- `warnings: List[str]` - Warning messages

**Methods:**
- `.verdict` - Property that computes overall PASS/FAIL/ERROR
- `.exit_code` - Property that maps verdict to exit code
- `.summary` - Property with session/metric statistics
- `.add_session()` - Add a test session
- `.finalize()` - Compute hash, duration, verdict
- `.to_dict()` - Convert to dictionary
- `.to_json()` - Serialize to JSON string

**When to use:** ALWAYS for final output. This is the singular contract.

### SessionResult (Evaluation Schema)

**Location:** `systemeval/core/evaluation.py`

**Purpose:** Results for a single logical test session

**Fields:**
- `session_id: str` - Unique identifier
- `session_name: str` - Human-readable name
- `metrics: List[MetricResult]` - Individual metrics
- `duration_seconds: float` - Session duration
- `stdout: str` - Captured stdout
- `stderr: str` - Captured stderr
- `artifacts: Dict[str, str]` - Links to artifacts

**CASCADE RULE:** If ANY metric fails, the session FAILS.

### MetricResult (Evaluation Schema)

**Location:** `systemeval/core/evaluation.py`

**Purpose:** Single measurable criterion with pass/fail condition

**Fields:**
- `name: str` - Metric identifier
- `value: Any` - Actual measured value
- `expected: Any` - Expected value or condition
- `passed: bool` - True if metric passed
- `message: Optional[str]` - Human-readable description
- `severity: str` - error, warning, info

**Examples:**
- `build_status`, `test_count`, `error_rate`, `coverage_percent`

## Verdict Cascade Logic

```
MetricResult.passed = False
         ▼
SessionResult.verdict = FAIL  (ANY metric fails → session FAILS)
         ▼
EvaluationResult.verdict = FAIL  (ANY session fails → evaluation FAILS)
         ▼
exit_code = 1
```

**Verdict Rules:**
- `PASS`: All sessions pass, all metrics pass
- `FAIL`: Any metric fails, any session fails
- `ERROR`: System/configuration error (exit_code=2, no tests collected, etc.)

## Factory Functions

### create_evaluation()

Creates an EvaluationResult with proper metadata:

```python
from systemeval.core import create_evaluation

result = create_evaluation(
    adapter_type="pytest",
    category="unit",
    project_name="my-project",
    command="pytest tests/",
)
```

Auto-captures:
- Unique evaluation_id (UUID4)
- Timestamp with microseconds
- Git commit, branch
- Host, Python version, platform

### create_session()

Creates a SessionResult:

```python
from systemeval.core import create_session

session = create_session("unit-tests")
session.metrics.append(...)
result.add_session(session)
```

### metric()

Creates a MetricResult:

```python
from systemeval.core import metric

m = metric(
    name="tests_passed",
    value=150,
    expected=">0",
    condition=True,
    message="150 tests passed"
)
```

## Migration Guide

### If you're using result.py classes:

**Before:**
```python
from systemeval.core.result import SequenceResult, SessionResult

seq = SequenceResult(sequence_id="...", sequence_name="...")
session = SessionResult(session_id="...", session_name="...")
# ...
```

**After:**
```python
from systemeval.core import create_evaluation, create_session, metric

evaluation = create_evaluation(adapter_type="pytest")
session = create_session("unit-tests")
session.metrics.append(metric(...))
evaluation.add_session(session)
evaluation.finalize()
```

### If you're outputting TestResult directly:

**Before:**
```python
result = adapter.execute(tests)
print(json.dumps(result.to_dict()))  # Incomplete schema
```

**After:**
```python
result = adapter.execute(tests)
evaluation = result.to_evaluation(adapter_type="pytest")
evaluation.finalize()
print(evaluation.to_json())  # Complete schema
```

## File Reference

| File | Status | Purpose |
|------|--------|---------|
| `adapters/base.py` | **ACTIVE** | TestResult intermediate format |
| `core/evaluation.py` | **ACTIVE** | EvaluationResult PRIMARY schema |
| `core/result.py` | **DEPRECATED** | Legacy SequenceResult (to be removed) |
| `core/reporter.py` | **ACTIVE** | Uses EvaluationResult for output |
| `core/__init__.py` | **ACTIVE** | Exports evaluation.py classes only |

## Non-Negotiable Rules

1. **Adapters return TestResult** - Never return EvaluationResult directly from execute()
2. **Always call .to_evaluation()** - Never output TestResult directly
3. **Always call .finalize()** - Before outputting EvaluationResult
4. **Never use result.py** - It's deprecated and will be removed
5. **One schema for output** - EvaluationResult is the singular contract

## Questions?

**Q: When should I use TestResult?**
A: Only when implementing an adapter. Return it from `.execute()`.

**Q: When should I use EvaluationResult?**
A: Always for final output. This is the canonical schema.

**Q: Can I use SequenceResult from result.py?**
A: No. It's deprecated. Use EvaluationResult instead.

**Q: How do I know if I'm using the right schema?**
A: If you're calling `.to_json()`, it should be on EvaluationResult, not TestResult.

**Q: What's the difference between SessionResult in result.py and evaluation.py?**
A: They're different classes with the same name. Use evaluation.py version only.

## Summary

- **TestResult** = Intermediate format from adapters
- **EvaluationResult** = Final output schema (PRIMARY)
- **result.py** = Deprecated legacy code (DO NOT USE)
- **Flow:** Adapter → TestResult → .to_evaluation() → EvaluationResult → JSON
