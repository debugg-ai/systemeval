# Pipeline Adapter

## Overview

The PipelineAdapter integrates DebuggAI's full pipeline testing (build → deploy → health → crawl → E2E tests) with the systemeval framework. It provides deterministic pass/fail evaluation based on hardcoded criteria.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     PipelineAdapter                             │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. discover()                                                  │
│     └─> Query Django: Project.objects.all()                    │
│     └─> Return TestItem per project                            │
│                                                                 │
│  2. execute()                                                   │
│     ├─> For each project:                                      │
│     │   ├─> _trigger_webhook()                                 │
│     │   │   └─> Call process_push_webhook task                 │
│     │   ├─> _poll_for_completion()                             │
│     │   │   ├─> Check Build.status                             │
│     │   │   ├─> Check Container.is_healthy                     │
│     │   │   ├─> Check KnowledgeGraph exists                    │
│     │   │   ├─> Count GraphPage                                │
│     │   │   └─> Calculate E2eRun error rate                    │
│     │   ├─> _metrics_pass()                                    │
│     │   │   └─> Evaluate all CRITERIA                          │
│     │   └─> Return PASS/FAIL                                   │
│     └─> Aggregate TestResult                                   │
│                                                                 │
│  3. validate_environment()                                      │
│     └─> Check Django apps installed                            │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

## Hardcoded Criteria

```python
CRITERIA = {
    "build_status": lambda v: v == "succeeded",
    "container_healthy": lambda v: v is True,
    "kg_exists": lambda v: v is True,
    "kg_pages": lambda v: v is not None and v > 0,
    "e2e_error_rate": lambda v: v == 0 or v == 0.0,
}
```

**ALL criteria must pass for a project to be marked as PASS.**

## Django Models Used

| Model | Field | Purpose |
|-------|-------|---------|
| `Project` | id, name, slug, repo | Project discovery |
| `Build` | status, timestamp, completed_at | Build status checking |
| `Container` | is_healthy, health_checks_passed | Container health |
| `KnowledgeGraph` | environment__project | Graph existence |
| `GraphPage` | graph | Page count |
| `E2eRun` | outcome, timestamp, project | E2E outcome tracking |
| `E2eRunMetrics` | num_steps, run | E2E action count |
| `PipelineExecution` | status, metadata | Pipeline tracking |
| `RepositoryInstallation` | repo, github_repo_id | GitHub auth |

## Webhook Simulation

The adapter triggers pipelines by simulating GitHub push webhooks:

```python
payload = {
    "ref": "refs/heads/main",
    "after": "<commit_sha>",
    "repository": {
        "id": <repo_id>,
        "name": "<repo_name>",
        "full_name": "<owner>/<repo_name>",
        "html_url": "<repo_url>",
    },
    "pusher": {"name": "systemeval", "email": "eval@debugg.ai"},
    "commits": [...],
}

process_push_webhook.delay(payload_hash, payload, repo.id)
```

## Polling Loop

The adapter polls for completion using exponential backoff:

1. Check `Build.status` every `poll_interval` seconds
2. Check `Container.is_healthy` when build succeeds
3. Check `KnowledgeGraph` exists when container is healthy
4. Count `GraphPage` entries
5. Filter `E2eRun` by session timestamp (avoid historical runs)
6. Calculate `e2e_error_rate` from session runs only
7. Exit when:
   - All criteria pass OR
   - Timeout reached OR
   - Pipeline status is terminal (completed/failed)

## Session-Scoped Metrics

**Critical:** E2E metrics are filtered to the current evaluation session to avoid counting historical runs:

```python
session_start_dt = timezone.datetime.fromtimestamp(session_start, tz=timezone.utc)

# Only count runs from THIS evaluation session
session_runs = E2eRun.objects.filter(
    Q(project=project, timestamp__gte=session_start_dt) |
    Q(pipeline_execution=pe)
)

metrics["e2e_runs"] = session_runs.count()
metrics["e2e_error"] = session_runs.filter(outcome="error").count()
metrics["e2e_error_rate"] = (metrics["e2e_error"] / metrics["e2e_runs"]) * 100
```

Without session filtering, old E2E runs would pollute the metrics.

## Failure Messages

The adapter generates detailed failure messages:

```python
def _get_failure_message(metrics: Dict[str, Any]) -> str:
    """Generate failure message from metrics."""
    failures = []

    if metrics["build_status"] != "succeeded":
        failures.append(f"Build failed: {metrics['build_status']}")

    if not metrics["container_healthy"]:
        failures.append("Container not healthy")

    if not metrics["kg_exists"]:
        failures.append("Knowledge graph does not exist")

    if metrics["kg_pages"] == 0:
        failures.append(f"Knowledge graph has {metrics['kg_pages']} pages (required: > 0)")

    if metrics["e2e_error_rate"] > 0:
        failures.append(f"E2E error rate: {metrics['e2e_error_rate']:.1f}% (required: 0%)")

    return "; ".join(failures) if failures else "Unknown failure"
```

## Integration Points

### With run_system_eval.py

The adapter mirrors the logic from the Django management command:

| Feature | Management Command | PipelineAdapter |
|---------|-------------------|-----------------|
| Project discovery | `Project.objects.filter(...)` | `discover()` |
| Webhook trigger | `process_push_webhook.delay()` | `_trigger_webhook()` |
| Polling loop | Manual while loop | `_poll_for_completion()` |
| Metrics collection | Inline queries | `_collect_metrics()` |
| Criteria evaluation | `_metrics_would_pass()` | `_metrics_pass()` |
| Output | Custom table | `TestResult` (standardized) |

### With systemeval Framework

The adapter implements the BaseAdapter interface:

```python
class PipelineAdapter(BaseAdapter):
    def discover(...) -> List[TestItem]:
        """Find projects to test."""

    def execute(...) -> TestResult:
        """Run pipeline tests."""

    def validate_environment() -> bool:
        """Check Django is configured."""

    def get_available_markers() -> List[str]:
        """Return ['pipeline', 'build', 'health', 'crawl', 'e2e']."""
```

## Configuration Options

### adapter_config in systemeval.yaml

```yaml
adapter_config:
  # Projects to test (by slug or name)
  projects:
    - crochet-patterns
    - test-nextjs-simple

  # Max time to wait per project (seconds)
  timeout: 600

  # Polling frequency (seconds)
  poll_interval: 15

  # Run synchronously (blocking)
  sync_mode: false

  # Skip build phase
  skip_build: false
```

### Execute Parameters

```python
result = adapter.execute(
    tests=None,           # Specific TestItem list or None for all
    parallel=False,       # Unused (always sequential)
    coverage=False,       # Unused
    failfast=False,       # Stop on first failure
    verbose=False,        # Print progress
    timeout=600,          # Max time per project (seconds)
)
```

## Error Handling

### Project Not Found

```python
def _find_project(slug: str):
    """Find project by slug or name."""
    project = Project.objects.filter(slug__icontains=slug).first()
    if project:
        return project
    project = Project.objects.filter(name__icontains=slug).first()
    return project  # None if not found
```

Returns `None` if project doesn't exist. The adapter skips it and adds a warning.

### Webhook Trigger Failure

```python
def _trigger_webhook(project, ...) -> bool:
    """Trigger webhook. Returns True if successful."""
    try:
        # ... build payload ...
        process_push_webhook.delay(payload_hash, payload, repo.id)
        return True
    except Exception as e:
        logger.exception(f"Failed to trigger webhook for {project.name}")
        return False
```

If webhook fails to trigger, the project is marked as FAIL with metrics:
```python
{
    "build_status": "not_triggered",
    "container_healthy": False,
    "kg_exists": False,
    "kg_pages": 0,
    "e2e_error_rate": 0.0,
}
```

### Timeout Handling

If polling exceeds `timeout`:

1. Collect current metrics (may be incomplete)
2. Evaluate criteria (likely FAIL)
3. Return TestFailure with collected state

Example:
```
Build: succeeded
Container: healthy
KG: exists
Pages: 0  <-- Still crawling when timeout hit
E2E Error Rate: 0.0
Result: FAIL (kg_pages == 0)
```

## Performance Characteristics

### Per-Project Timing

| Phase | Duration | Impact on Timeout |
|-------|----------|------------------|
| Webhook trigger | 0.1-1s | Minimal |
| Build | 3-8min | Moderate |
| Deploy | 1-2min | Moderate |
| Health checks | 1-5min | Moderate |
| Crawl | 2-5min | Moderate |
| E2E generation | 1-3min | Moderate |
| E2E execution | 3-10min | High |
| **Total** | **11-33min** | **Full timeout** |

### Recommended Timeouts

- Single project: 600s (10 min)
- 3 projects: 1800s (30 min)
- 10 projects: 3600s (60 min)

### Polling Frequency

- Default: 15s
- Aggressive: 5s (more DB queries)
- Conservative: 30s (slower detection)

## Testing

### Unit Tests

```python
def test_criteria_evaluation():
    adapter = PipelineAdapter('/path/to/backend')

    # Test passing metrics
    metrics = {
        "build_status": "succeeded",
        "container_healthy": True,
        "kg_exists": True,
        "kg_pages": 10,
        "e2e_error_rate": 0.0,
    }
    assert adapter._metrics_pass(metrics) is True

    # Test failing metrics (build failed)
    metrics["build_status"] = "failed"
    assert adapter._metrics_pass(metrics) is False
```

### Integration Tests

```python
def test_full_pipeline():
    adapter = PipelineAdapter('/path/to/backend')

    # Discover projects
    tests = adapter.discover()
    assert len(tests) > 0

    # Execute (with short timeout for testing)
    result = adapter.execute(tests=tests[:1], timeout=300, verbose=True)

    # Check result structure
    assert result.total == 1
    assert result.verdict in [Verdict.PASS, Verdict.FAIL]
```

## Debugging

### Enable Verbose Output

```python
result = adapter.execute(verbose=True)
```

Output:
```
--- Evaluating: crochet-patterns ---
  Task queued: abc123-def456
  [+15s] build=pending container=pending e2e=0/0 (pending=0)
  [+30s] build=in_progress container=pending e2e=0/0 (pending=0)
  [+240s] build=succeeded container=healthy e2e=5/10 (pending=5)
  [+360s] build=succeeded container=healthy e2e=10/10 (pending=0)
  -> PASS (365.2s)
```

### Check Django Logs

```bash
docker-compose -f local.yml logs django -f | grep -E 'push|BUILD|PROVISION'
```

### Check Celery Workers

```bash
docker-compose -f local.yml logs celeryworker -f | grep process_push_webhook
```

### Query Metrics Directly

```python
from backend.builds.models import Build
from backend.containers.models import Container
from backend.e2es.models import E2eRun

project = Project.objects.get(slug='crochet-patterns')

print(f"Build: {Build.objects.filter(project=project).order_by('-timestamp').first().status}")
print(f"Container: {Container.objects.filter(project=project).order_by('-timestamp').first().is_healthy}")
print(f"E2E runs: {E2eRun.objects.filter(project=project).count()}")
print(f"E2E errors: {E2eRun.objects.filter(project=project, outcome='error').count()}")
```

## Future Enhancements

### Parallel Execution

Currently sequential. Could parallelize with:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(self._evaluate_project, p, ...) for p in projects]
    results = [f.result() for f in futures]
```

### Custom Criteria

Allow configuration to override criteria:

```yaml
adapter_config:
  custom_criteria:
    e2e_pass_rate: ">= 50.0"
    e2e_avg_actions: ">= 5"
```

### Incremental Reporting

Stream results as they complete:

```python
def execute_streaming(self, tests, ...):
    for test in tests:
        result = self._evaluate_project(...)
        yield result  # Stream to caller
```

### Retry Logic

Retry failed builds with suggested fixes:

```python
if build.status == "failed" and build.suggested_fixes:
    # Apply fixes and retry
    build2 = retry_build(build, apply_fixes=True)
```

## See Also

- [BaseAdapter Interface](/Users/quinnosha/Documents/Github/debugg-ai/full-platform/systemeval/systemeval/adapters/base.py)
- [Django Management Command](/Users/quinnosha/Documents/Github/debugg-ai/full-platform/sentinal/backend/backend/pipelines/management/commands/run_system_eval.py)
- [PIPELINE_CRITERIA](/Users/quinnosha/Documents/Github/debugg-ai/full-platform/sentinal/backend/backend/core/testing/criteria.py)
- [systemeval Documentation](../../README.md)
