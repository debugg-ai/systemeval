# SystemEval

[![PyPI](https://img.shields.io/pypi/v/systemeval)](https://pypi.org/project/systemeval/)
[![Python](https://img.shields.io/pypi/pyversions/systemeval)](https://pypi.org/project/systemeval/)

A unified evaluation framework providing objective, deterministic, and traceable test execution across any project.

**Homepage**: [debugg.ai](https://debugg.ai) | **Docs**: [debugg.ai/docs/systemeval](https://debugg.ai/docs/systemeval)

> See [COMMANDMENTS.md](COMMANDMENTS.md) for the core principles and design philosophy.

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
  "duration_seconds": 12.345,
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
| `systemeval docker status` | Show Docker container status |
| `systemeval docker logs` | View container logs |
| `systemeval docker exec` | Execute command in test container |
| `systemeval docker ready` | Check if containers are healthy |

## Design Requirements

- Do not introduce hard-coded strings/numbers; use configuration files, constants, or environment variables for values that may change between environments.
- Keep modules focused and digestible—split files that exceed ~600 lines and avoid functions longer than a screen so reasoning and tests stay simple.
- Maintain clear separation of concerns: configuration, command parsing, orchestration, and environment management should live in distinct layers.
- Document any deliberate exceptions to these rules (legacy constraints, temporary hacks) so reviewers know the rationale.

### Test Options

```bash
systemeval test [OPTIONS]

Options:
  -c, --category TEXT         Test category (unit, integration, api, e2e)
  -a, --app TEXT              Specific app/module to test
  -f, --file TEXT             Specific test file to run
  -p, --parallel              Run tests in parallel
  --coverage                  Collect coverage data
  -x, --failfast              Stop on first failure
  -v, --verbose               Verbose output
  --json                      Output results as JSON
  -t, --template TEXT         Output template name
  --env-mode [auto|docker|local]  Execution environment (default: auto)
  --config PATH               Path to config file
  -e, --env TEXT              Environment to run in
  -s, --suite TEXT            Test suite to run
  --keep-running              Keep services running after tests
  --attach                    Attach to running containers (skip build/up)
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

## Docker Compose Environments

SystemEval provides first-class Docker Compose support with auto-discovery, lifecycle management, and remote Docker host support.

### Quick Start

```yaml
# Minimal config - auto-discovers everything from docker-compose.yml
environments:
  backend:
    type: docker-compose
```

SystemEval will automatically:
- Find compose files (`docker-compose.yml`, `compose.yml`, `local.yml`, etc.)
- Detect services with source mounts as test candidates
- Infer test commands from `pytest.ini`, `package.json`, etc.
- Extract health check endpoints from compose healthchecks
- Configure appropriate ports

### Full Configuration

```yaml
environments:
  backend:
    type: docker-compose
    compose_file: local.yml           # Compose file (auto-detected if omitted)
    services: [django, postgres, redis]  # Services to manage (all if omitted)
    test_service: django              # Container to run tests in
    test_command: pytest              # Test command (auto-detected)
    working_dir: .                    # Project directory

    # Health check (auto-detected from compose healthcheck)
    health_check:
      endpoint: /api/health/
      port: 8000
      timeout: 120

    # Remote Docker host (optional)
    docker:
      host: ssh://user@remote-server
      # Or use Docker context
      context: my-remote-context
```

### Attach Mode

Connect to already-running containers without lifecycle management:

```yaml
environments:
  dev:
    type: docker-compose
    attach: true  # Skip build/up, just exec into running containers
    test_service: django
```

```bash
# Containers already running from docker compose up
systemeval test --env dev --attach
```

### Auto-Discovery

SystemEval searches for compose files in priority order:
1. `docker-compose.yml`
2. `docker-compose.yaml`
3. `compose.yml`
4. `compose.yaml`
5. `local.yml` / `local.yaml`
6. `dev.yml` / `dev.yaml`

From the compose file, it infers:
- **Test service**: First service with source mount + build context
- **Health port**: From port mapping (e.g., `8000:8000` → port 8000)
- **Health endpoint**: From compose healthcheck command
- **Test command**: From `pytest.ini`, `package.json`, `pyproject.toml`

### CLI Commands

```bash
# Run tests in Docker environment
systemeval test --env backend

# Attach to running containers
systemeval test --env backend --attach

# Docker-specific commands
systemeval docker status              # Show container status
systemeval docker logs [service]      # View container logs
systemeval docker exec <cmd>          # Execute command in test container
systemeval docker ready               # Check if containers are healthy
```

### Pre-flight Checks

Before starting containers, SystemEval validates:
- Docker binary is installed
- Docker daemon is running
- Docker Compose V2 is available
- Compose file exists and is valid YAML
- Referenced services exist in compose file
- Test service is defined

### Remote Docker Hosts

Run tests against remote Docker daemons:

```yaml
environments:
  staging:
    type: docker-compose
    docker:
      host: ssh://deploy@staging.example.com
    attach: true  # Usually attach to remote, don't manage lifecycle
```

Or use Docker contexts:

```bash
docker context create staging --docker "host=ssh://deploy@staging.example.com"
```

```yaml
environments:
  staging:
    type: docker-compose
    docker:
      context: staging
```

### Example Projects

See `example-usage-projects/` for complete working examples:

| Project | Compose File | Stack | Test Framework |
|---------|-------------|-------|----------------|
| `django-rest-api/` | `docker-compose.yml` | Django + Postgres + Redis | pytest |
| `express-mongo-api/` | `compose.yml` | Express + MongoDB | jest |
| `fastapi-react-fullstack/` | `local.yml` | FastAPI + React + Postgres + nginx | pytest + jest |

### Standalone Environments

For non-Docker services:

```yaml
environments:
  frontend:
    type: standalone
    command: npm run dev
    test_command: npm test
    ready_endpoint: http://localhost:3000
```

### Running Tests

```bash
# Run in specific environment
systemeval test --env backend

# Run in default environment
systemeval test

# Keep containers running after tests
systemeval test --env backend --keep-running
```

## Design Principles

1. **Deterministic**: Same inputs always produce same verdict
2. **Objective**: No subjective interpretation of results
3. **Traceable**: Every run is uniquely identifiable
4. **Machine-First**: JSON output designed for automation
5. **Framework-Agnostic**: Adapters hide implementation details
6. **CI-Native**: Exit codes and output formats for pipelines

## Design Requirements

- Avoid embedding "magic" strings or numbers; prefer constants, YAML fields, or env vars so behavior is configurable.
- Break files that grow beyond ~600 lines into cohesive, testable pieces and keep functions short unless the domain demand special handling.
- Enforce single-responsibility layering: parsing, orchestration, and runtime helpers should be maintained in separate modules.
- Document intentional deviations so future agents understand why the rule was relaxed.
- Refer to `../docs/crawl-e2e-api-reference.md` before wiring CLI integrations to reuse the documented crawl and E2E API shapes.

## ⏺ The Testing Philosophy

### The Process
1. Investigate Why Tests Missed It
2. Write Test That FAILS
3. Fix The Code
4. Test Now PASSES

### The Philosophy
Never fix a bug you can't reproduce in a test.

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

## Links

- **Homepage**: [debugg.ai](https://debugg.ai)
- **Documentation**: [debugg.ai/docs/systemeval](https://debugg.ai/docs/systemeval)
- **Repository**: [github.com/debugg-ai/systemeval](https://github.com/debugg-ai/systemeval)
- **PyPI**: [pypi.org/project/systemeval](https://pypi.org/project/systemeval/)

## License

MIT License - see [LICENSE](LICENSE) for details.
