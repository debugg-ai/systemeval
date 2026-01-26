# Pipeline Adapter

The Pipeline adapter integrates DebuggAI's full pipeline testing with systemeval. It triggers complete pipeline workflows (GitHub webhook → build → deploy → health → crawl → E2E tests) and evaluates success based on deterministic criteria.

## Installation

The Pipeline adapter requires Django and DebuggAI backend dependencies:

```bash
# Install systemeval with pipeline support
pip install systemeval

# Ensure Django is configured
export DJANGO_SETTINGS_MODULE=config.settings.local
```

## Configuration

### Basic Configuration

```yaml
framework: pipeline
project_root: /path/to/sentinal/backend

adapter_config:
  projects:
    - crochet-patterns
    - test-nextjs-simple
  timeout: 600
  poll_interval: 15
```

### Adapter Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `projects` | list[str] | [] | Project slugs or names to test |
| `timeout` | int | 600 | Max time to wait per project (seconds) |
| `poll_interval` | int | 15 | Polling frequency for status checks (seconds) |
| `sync_mode` | bool | false | Run webhooks synchronously (blocking) |
| `skip_build` | bool | false | Skip build phase, use existing containers |

## Pass Criteria

The Pipeline adapter evaluates projects based on **hardcoded, non-negotiable** criteria:

| Criterion | Evaluator | Failure Message |
|-----------|-----------|-----------------|
| `build_status` | `== "succeeded"` | Build failed |
| `container_healthy` | `== True` | Container not healthy |
| `kg_exists` | `== True` | Knowledge graph does not exist |
| `kg_pages` | `> 0` | Knowledge graph has 0 pages |
| `e2e_error_rate` | `== 0` | E2E error rate > 0% (errors are system bugs) |

**All criteria must pass for a project to be marked as PASS.**

## Test Discovery

The adapter discovers projects from the Django database:

```python
from systemeval.adapters import get_adapter

adapter = get_adapter('pipeline', '/path/to/sentinal/backend')
tests = adapter.discover()

# Returns TestItem objects:
# [
#     TestItem(
#         id='123',
#         name='crochet-patterns',
#         path='crochet-patterns',
#         markers=['pipeline', 'build', 'health', 'crawl', 'e2e'],
#         metadata={'project_id': 123, 'project_slug': 'crochet-patterns'}
#     ),
#     ...
# ]
```

## Test Execution

### Full Pipeline Flow

```
TRIGGER → BUILD (3-8min) → DEPLOY (1-2min) → HEALTH (1-5min) → CRAWL (2-5min) → E2E GEN → E2E RUN (3-10min)
```

### Execution Phases

1. **Webhook Trigger**: Simulates GitHub push webhook
2. **Polling Loop**: Monitors pipeline progress every `poll_interval` seconds
3. **Metrics Collection**: Gathers metrics from Django models:
   - `Build.status`
   - `Container.is_healthy`
   - `KnowledgeGraph` existence
   - `GraphPage` count
   - `E2eRun` outcomes (filtered to session scope)
4. **Criteria Evaluation**: Checks all criteria pass
5. **Result Generation**: Returns `TestResult` with pass/fail/error counts

### Example

```python
from systemeval.adapters import get_adapter

adapter = get_adapter('pipeline', '/path/to/sentinal/backend')

# Execute all projects
result = adapter.execute(
    tests=None,  # All projects
    timeout=600,  # 10 minutes per project
    verbose=True,
)

print(f"Passed: {result.passed}")
print(f"Failed: {result.failed}")
print(f"Errors: {result.errors}")
print(f"Verdict: {result.verdict}")  # PASS/FAIL/ERROR
```

## CLI Usage

### Run Pipeline Tests

```bash
# Run on all discovered projects
systemeval run --adapter pipeline --project-root /path/to/sentinal/backend

# Run on specific projects
systemeval run --config examples/pipeline_example.yaml

# Verbose output with timeout
systemeval run \
  --adapter pipeline \
  --project-root /path/to/sentinal/backend \
  --verbose \
  --timeout 1800
```

### Expected Output

```
======================================================================
 EVALUATION RESULTS
======================================================================
Duration: 180.5s
Projects: 1/1 passed

Project                   Build        Container  KG Pages   E2E P/F/E    Result
----------------------------------------------------------------------------------
crochet-patterns          succeeded    healthy    37         13/78/0      PASS
test-nextjs-simple        succeeded    healthy    12         5/3/0        PASS
test-vue-vite-simple      failed       pending    0          0/0/0        FAIL
----------------------------------------------------------------------------------

Aggregate Metrics:
  Builds: 2/3 succeeded
  Containers: 2/3 healthy
  E2E Runs: 99
  E2E Passed: 18
  E2E Failed: 81
  E2E Errors: 0 (CRITICAL: Errors are system bugs, must be 0)
  Pass Rate: 18.2%
  Error Rate: 0.0%
```

## Markers

The Pipeline adapter provides the following markers for filtering:

- `pipeline` - Full pipeline tests
- `build` - Build-related tests
- `health` - Health check tests
- `crawl` - Crawler/knowledge graph tests
- `e2e` - E2E test execution

```yaml
filters:
  category: e2e  # Only run E2E-related checks
```

## Environment Validation

The adapter validates the Django environment before execution:

```python
adapter = get_adapter('pipeline', '/path/to/sentinal/backend')

if adapter.validate_environment():
    print("Environment is valid")
else:
    print("Environment validation failed")
```

Validation checks:

- Django is configured
- Required apps are installed:
  - `backend.projects`
  - `backend.builds`
  - `backend.containers`
  - `backend.graphs`
  - `backend.e2es`

## Integration with Django Management Commands

The Pipeline adapter mirrors the logic from `run_system_eval.py`:

```bash
# Django management command (old way)
docker-compose -f local.yml exec django python manage.py run_system_eval --projects crochet-patterns

# systemeval CLI (new way)
systemeval run --adapter pipeline --project-root /path/to/sentinal/backend
```

**Key differences:**

- systemeval provides standardized JSON output
- systemeval supports multi-framework testing in one config
- systemeval has unified reporting across all adapters
- Django command remains available for Docker exec usage

## Troubleshooting

### "No projects found to test"

Ensure projects exist in the database and `project_root` points to the Django backend:

```python
from backend.projects.models import Project
print(Project.objects.all())
```

### "Django is not configured"

Set `DJANGO_SETTINGS_MODULE` before running:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.local
systemeval run --adapter pipeline --project-root /path/to/sentinal/backend
```

### "Build triggered but never completes"

Check Celery workers are running:

```bash
docker-compose -f local.yml logs celeryworker -f | grep -E 'push|BUILD'
```

### "E2E error rate > 0%"

E2E errors indicate **system bugs**, not test failures. Check:

1. Surfer metadata for error details
2. Browser session logs
3. CDP connection errors

```bash
docker-compose -f local.yml logs celerybrowser --tail=100 | grep ERROR
```

## Advanced Usage

### Custom Project Selection

```python
from systemeval.adapters import get_adapter
from backend.projects.models import Project

adapter = get_adapter('pipeline', '/path/to/sentinal/backend')

# Discover all projects
all_tests = adapter.discover()

# Filter to specific projects
selected_tests = [t for t in all_tests if t.name in ['crochet-patterns', 'test-nextjs-simple']]

# Execute only selected
result = adapter.execute(tests=selected_tests, timeout=600, verbose=True)
```

### Skip Build Phase

For faster iteration when containers are already deployed:

```yaml
adapter_config:
  skip_build: true
  timeout: 300  # Shorter timeout since build is skipped
```

### Synchronous Execution

For debugging or CI/CD environments where you want blocking execution:

```yaml
adapter_config:
  sync_mode: true
  timeout: 900
```

**Warning:** Synchronous mode blocks the webhook handler until completion. Use sparingly.

## Metrics Collected

The adapter collects the following metrics per project:

### Build Metrics
- `build_status`: succeeded/failed/timeout/cancelled
- `build_duration_seconds`: Build time in seconds

### Container Metrics
- `container_healthy`: Boolean
- `health_checks_passed`: Count (requires >= 3)

### Knowledge Graph Metrics
- `kg_exists`: Boolean
- `kg_pages`: Count of pages in graph

### E2E Metrics (Session-Scoped)
- `e2e_runs`: Total E2E runs in this session
- `e2e_passed`: Runs with outcome='pass'
- `e2e_failed`: Runs with outcome='fail'
- `e2e_error`: Runs with outcome='error' (MUST be 0)
- `e2e_error_rate`: Percentage of error runs
- `e2e_avg_actions`: Average actions per run

**Important:** E2E metrics are scoped to the evaluation session (since pipeline trigger) to avoid counting historical runs.

## Performance Expectations

| Stage | Expected Duration | Timeout if Exceeded |
|-------|------------------|---------------------|
| Build | 3-8 minutes | 15 minutes |
| Deploy | 1-2 minutes | 5 minutes |
| Health | 1-5 minutes | 10 minutes |
| Crawl | 2-5 minutes | 10 minutes |
| E2E Gen | 1-3 minutes | 5 minutes |
| E2E Run | 3-10 minutes | 15 minutes |
| **Total** | **11-33 minutes** | **60 minutes** |

Default `timeout=600` (10 minutes) is suitable for single projects. For multiple projects, increase accordingly.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Pipeline Tests

on: [push]

jobs:
  pipeline-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install systemeval
        run: pip install systemeval

      - name: Run pipeline tests
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
        run: |
          systemeval run \
            --adapter pipeline \
            --project-root ./sentinal/backend \
            --json \
            --output results.json

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: pipeline-results
          path: results.json
```

## See Also

- [Base Adapter Documentation](base.md)
- [Pytest Adapter Documentation](pytest.md)
- [systemeval CLI Reference](../cli.md)
- [Django Management Command: run_system_eval](../../sentinal/CLAUDE.md)
