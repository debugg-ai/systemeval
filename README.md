# SystemEval

A unified evaluation framework providing objective, deterministic, and traceable test execution across any project.

## Philosophy

SystemEval exists to solve a fundamental problem: **test results should be facts, not opinions**.

Traditional test runners produce ambiguous output that requires human interpretation. Did the build pass? Sort of. Are we ready to deploy? Probably. SystemEval eliminates this ambiguity with three core principles:

### 1. Objective Verdicts

Every evaluation produces one of three verdicts: `PASS`, `FAIL`, or `ERROR`. There is no "mostly passing" or "acceptable failure rate." The verdict is computed deterministically from metrics using cascade logic:

```
ANY metric fails    --> session FAILS
ANY session fails   --> sequence FAILS
exit_code == 2      --> ERROR (collection/config problem)
total == 0          --> ERROR (nothing ran)
```

### 2. Non-Fungible Runs

Every evaluation run is uniquely identifiable and traceable:

- **Run ID**: UUID for the specific execution
- **Timestamp**: ISO 8601 UTC timestamp
- **Exit Code**: 0 (PASS), 1 (FAIL), or 2 (ERROR)

Same inputs always produce the same verdict. If a test is flaky, it fails - there is no retry-until-green.

### 3. Machine-Parseable Output

Results are structured data first, human-readable second:

- JSON schema for programmatic consumption
- Jinja2 templates for human-friendly formats
- Designed for CI pipelines, agentic review, and automated comparison

## Installation

```bash
# From PyPI
pip install systemeval

# With pytest support (recommended)
pip install systemeval[pytest]

# From source
git clone https://github.com/debugg-ai/systemeval
cd systemeval
pip install -e ".[pytest]"
```

**Requirements**: Python 3.9+

## Quick Start

### Initialize Configuration

```bash
cd your-project
systemeval init
```

This creates `systemeval.yaml` with auto-detected settings for your project type (Django, Next.js, generic Python, etc.).

### Run Tests

```bash
# Run all tests
systemeval test

# Run specific category
systemeval test --category unit

# Run with JSON output for CI
systemeval test --json

# Run with specific template
systemeval test --template markdown
```

### Check Results

```bash
# Exit code tells you everything
systemeval test && echo "PASS" || echo "FAIL"
```

## Configuration

Create `systemeval.yaml` in your project root:

```yaml
# Adapter: which test framework to use
adapter: pytest

# Project metadata
project_root: .
test_directory: tests

# Test categories with markers
categories:
  unit:
    description: "Fast isolated unit tests"
    markers: [unit]
  integration:
    description: "Tests with external dependencies"
    markers: [integration]
  api:
    description: "API endpoint tests"
    markers: [api]
  e2e:
    description: "End-to-end browser tests"
    markers: [e2e]
    requires: [browser]
```

## Output Schema

Every test run produces a result conforming to this schema:

```json
{
  "verdict": "PASS | FAIL | ERROR",
  "exit_code": 0,
  "timestamp": "2024-01-15T10:30:00.000Z",
  "total": 150,
  "passed": 148,
  "failed": 2,
  "errors": 0,
  "skipped": 5,
  "duration": 12.345,
  "category": "unit",
  "coverage_percent": 87.5
}
```

### Verdict Logic

| Condition | Verdict | Exit Code |
|-----------|---------|-----------|
| `exit_code == 2` | ERROR | 2 |
| `total == 0` | ERROR | 2 |
| `failed > 0 OR errors > 0` | FAIL | 1 |
| All tests pass | PASS | 0 |

### Extended Schema (Sequence Results)

For multi-session evaluations:

```json
{
  "sequence_id": "uuid",
  "sequence_name": "full-pipeline",
  "verdict": "PASS | FAIL",
  "exit_code": 0,
  "duration_seconds": 45.2,
  "pass_count": 3,
  "fail_count": 0,
  "sessions": [
    {
      "session_id": "uuid",
      "session_name": "unit-tests",
      "verdict": "PASS",
      "duration_seconds": 12.1,
      "metrics": [
        {
          "name": "tests_passed",
          "value": 150,
          "passed": true,
          "failure_message": null
        }
      ]
    }
  ]
}
```

## CLI Reference

### Commands

| Command | Description |
|---------|-------------|
| `systemeval test` | Run tests using configured adapter |
| `systemeval init` | Create configuration file |
| `systemeval validate` | Validate configuration |
| `systemeval list categories` | Show available test categories |
| `systemeval list adapters` | Show available test adapters |
| `systemeval list templates` | Show available output templates |
| `systemeval list environments` | Show configured environments |

### Test Options

```bash
systemeval test [OPTIONS]

Options:
  -c, --category TEXT      Test category (unit, integration, api, e2e)
  -a, --app TEXT           Specific app/module to test
  -f, --file TEXT          Specific test file to run
  -p, --parallel           Run tests in parallel
  --coverage               Collect coverage data
  -x, --failfast           Stop on first failure
  -v, --verbose            Verbose output
  --json                   Output results as JSON
  -t, --template TEXT      Output template name
  --docker                 Force Docker environment
  --no-docker              Force local environment
  --config PATH            Path to config file
  -e, --env TEXT           Environment to run in
  -s, --suite TEXT         Test suite to run
  --keep-running           Keep services running after tests
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed (PASS) |
| 1 | One or more tests failed (FAIL) |
| 2 | Configuration, collection, or execution error (ERROR) |

## Output Templates

SystemEval includes built-in templates for different output needs:

| Template | Use Case |
|----------|----------|
| `summary` | One-line CI log output |
| `table` | ASCII table for terminal |
| `markdown` | Full report in markdown |
| `json` | Use `--json` flag instead |
| `junit` | JUnit XML for test tools |
| `github` | GitHub Actions annotations |
| `slack` | Slack message format |
| `ci` | Structured CI/CD format |

### Usage

```bash
# Terminal table
systemeval test --template table

# Markdown report
systemeval test --template markdown > report.md

# GitHub annotations
systemeval test --template github
```

### Custom Templates

Templates use Jinja2 syntax. Create custom templates:

```bash
# From file
systemeval test --template ./my-template.j2

# Available context variables:
# verdict, exit_code, total, passed, failed, errors, skipped
# duration, timestamp, category, coverage_percent
# pass_rate, failure_rate, verdict_emoji
# failures (list of failure details)
```

## Adapters

Adapters bridge SystemEval to specific test frameworks.

### Pytest (Default)

```yaml
adapter: pytest
```

Features:
- Test discovery via pytest collection API
- Marker-based category filtering
- Parallel execution (pytest-xdist)
- Coverage reporting (pytest-cov)
- Django auto-detection and configuration

### Jest (Coming Soon)

```yaml
adapter: jest
jest:
  config_file: jest.config.js
```

### Creating Custom Adapters

```python
from systemeval.adapters import BaseAdapter, TestResult, TestItem

class MyAdapter(BaseAdapter):
    def discover(self, category=None, app=None, file=None) -> list[TestItem]:
        # Return discovered tests
        pass

    def execute(self, tests=None, **kwargs) -> TestResult:
        # Run tests and return results
        pass

    def get_available_markers(self) -> list[str]:
        # Return available categories/markers
        pass

    def validate_environment(self) -> bool:
        # Check framework is configured
        pass
```

Register in the adapter registry:

```python
from systemeval.adapters import register_adapter
register_adapter("my-adapter", MyAdapter)
```

## Environments

SystemEval can orchestrate test environments (Docker Compose, standalone services).

```yaml
environments:
  backend:
    type: docker-compose
    compose_file: docker-compose.yml
    test_command: pytest
    default: true

  frontend:
    type: standalone
    command: npm run dev
    test_command: npm test
```

Run tests in specific environment:

```bash
systemeval test --env backend
systemeval test --env frontend
```

## Design Principles

1. **Deterministic**: Same inputs always produce same verdict
2. **Objective**: No subjective interpretation of results
3. **Traceable**: Every run is uniquely identifiable
4. **Machine-First**: JSON output designed for automation
5. **Framework-Agnostic**: Adapters hide implementation details
6. **CI-Native**: Exit codes and output formats for pipelines

## Comparison with Other Tools

| Feature | SystemEval | pytest | jest |
|---------|------------|--------|------|
| Unified CLI | Yes | No | No |
| Framework agnostic | Yes | Python only | JS only |
| Strict verdicts | PASS/FAIL/ERROR | Exit codes vary | Exit codes vary |
| JSON schema | Versioned | Plugin required | Custom |
| Environment orchestration | Built-in | External | External |

## Contributing

See the adapter documentation in `systemeval/adapters/README.md` for details on extending SystemEval.

## License

MIT License - see [LICENSE](LICENSE) for details.
