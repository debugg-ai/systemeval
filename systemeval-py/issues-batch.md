## Pipeline Adapter Django Coupling
type: bug
priority: P0
labels: architecture, coupling

Direct Django ORM imports in adapter code violates adapter pattern:
- Line 162: `from backend.projects.models import Project`
- Line 389: `from backend.repos.models import RepositoryInstallation`
- Hardcoded Django app names: backend.projects, backend.builds, etc.

**Impact:** Adapter cannot work outside DebuggAI Django project, violates framework-agnostic design, testing requires full Django setup

**Fix:** Create abstraction layer (ProjectRepository interface), inject dependencies

## No Tests for PipelineAdapter - Critical coverage gap
type: bug
priority: P0
labels: testing, coverage

PipelineAdapter has 927 lines with ZERO test coverage. Most complex adapter in codebase.

**Missing coverage:**
- _setup_django() - Django settings detection
- _trigger_webhook() - GitHub webhook payload construction
- _poll_for_completion() - Polling logic with timeout
- _collect_metrics() - Metric collection from database
- create_evaluation_result() - EvaluationResult construction

**Fix:** Create tests/test_pipeline_adapter.py with mocked Django models

## No Tests for PytestAdapter - Default adapter untested
type: bug
priority: P0
labels: testing, coverage

PytestAdapter is the default adapter with ZERO test coverage.

**Missing coverage:**
- _detect_django() - Django settings detection
- discover() - Test discovery with markers
- execute() - Test execution
- PytestCollectPlugin behavior
- PytestResultPlugin behavior

**Fix:** Create comprehensive tests using pytest plugin testing utilities

## Missing Error Handling in Critical Paths
type: bug
priority: P1
labels: reliability, error-handling

Bare try/except blocks swallow errors:
- pipeline_adapter.py:104-106: Silently continues if Django setup fails
- pipeline_adapter.py:436-437: Generic "pass" on failures
- cli.py:558-559: Bare except catches all exceptions

**Impact:** Silent failures, debugging nightmares, unpredictable behavior

**Fix:** Specific exceptions, logging, proper error propagation

## Configuration Over-engineering - 6 models for simple YAML
type: improvement
priority: P1
labels: complexity, over-engineering

227 lines and 6 different config models for simple YAML. Most projects use 3-5 config options.

**Impact:** High barrier to entry, documentation burden, maintenance overhead

**Fix:** Simplify to 2-3 models, use TypedDict for flat configs

## Test Executor Regex Parsing Fragility
type: bug
priority: P1
labels: reliability, parsing

Brittle regex patterns for parsing test output (executor.py:251-321). Falls back to passed=1 or failed=1 guesses.

**Impact:** Incorrect test counts, misleading reports, false positives/negatives

**Fix:** Use structured output (JSON/XML), fallback should return ERROR verdict

## No Tests for DockerComposeEnvironment
type: bug
priority: P1
labels: testing, coverage

DockerComposeEnvironment handles Docker lifecycle with ZERO test coverage.

**Missing coverage:** setup(), wait_ready(), run_tests(), teardown()

**Fix:** Create tests/test_docker_compose_env.py

## No Tests for StandaloneEnvironment
type: bug
priority: P1
labels: testing, coverage

StandaloneEnvironment lacks test coverage for process lifecycle and pattern matching.

**Fix:** Create tests/test_standalone_env.py

## No Tests for Config Loading
type: bug
priority: P1
labels: testing, coverage

load_config() has no test coverage for malformed YAML, missing fields, invalid adapters.

**Fix:** Create tests/test_config.py

## TestResult.total Bug - Treats explicit 0 as not provided
type: bug
priority: P1
labels: bug, logic-error

In base.py:64-67, if total=0 (valid for "no tests collected"), it gets overwritten.

**Fix:** Use Optional[int] and check for None instead

## Missing Retry Logic in Pipeline Adapter
type: improvement
priority: P1
labels: reliability, networking

No retry on transient failures for health checks, webhook triggers, container polling.

**Impact:** Flaky tests due to timing issues

**Fix:** Add retry decorator with exponential backoff

## No Structured Logging Framework
type: improvement
priority: P1
labels: observability, logging

Inconsistent logging: some use logger, some console.print(), some print(). No log levels.

**Impact:** Debugging production issues impossible

**Fix:** Standardize on Python logging with structured JSON output

## Race Conditions in Pipeline Polling
type: bug
priority: P1
labels: concurrency, reliability

No synchronization for concurrent pipeline executions. Wrong metrics could be attributed to wrong session.

**Fix:** Filter queries by session start time, add execution ID correlation

## Timeout Not Enforced in Streaming Mode
type: bug
priority: P1
labels: reliability, timeout

readline() in executor.py:149-185 has no timeout and blocks forever if process hangs.

**Fix:** Use select or asyncio for non-blocking I/O

## Inconsistent Naming Conventions
type: improvement
priority: P2
labels: code-quality, consistency

Mixed naming: session_id vs sessionId, timestamp_utc vs started_at, duration_seconds vs duration.

**Fix:** Adopt strict Python conventions (snake_case), run linter

## Unnecessary Abstraction - Environment Hierarchy
type: improvement
priority: P2
labels: over-engineering, yagni

Complex environment hierarchy with minimal reuse. CompositeEnvironment likely unused.

**Fix:** Flatten to concrete implementations

## Code Duplication - Django Settings Detection
type: improvement
priority: P2
labels: code-quality, duplication

Identical Django detection logic in pipeline_adapter.py and pytest_adapter.py.

**Fix:** Extract to utils/django.py

## Dead Code - _parse_test_output in DockerCompose
type: bug
priority: P2
labels: code-quality, dead-code

docker_compose.py:241-277 defines _parse_test_output() but never calls it.

**Fix:** Remove dead code

## Bare Except in CLI Django Detection
type: bug
priority: P2
labels: error-handling, code-quality

cli.py:558 uses bare except which catches everything including KeyboardInterrupt.

**Fix:** Use specific exception types

## No Validation of Metric Severity Values
type: bug
priority: P2
labels: validation, type-safety

severity field accepts any string but should only be error/warning/info.

**Fix:** Use Enum or validate in __post_init__

## Boolean Trap in CLI Options
type: improvement
priority: P2
labels: api-design, usability

Multiple boolean flags with unclear relationships: docker/no_docker (mutually exclusive).

**Fix:** Use enums or exclusive option groups

## No Tests for Template Rendering
type: bug
priority: P2
labels: testing, coverage

templates/renderer.py and templates/defaults.py have no test coverage.

**Fix:** Create tests/test_templates.py

## No Tests for Docker Plugin
type: bug
priority: P2
labels: testing, coverage

plugins/docker.py functions are untested.

**Fix:** Create test_docker_plugin.py

## No Tests for DockerResourceManager
type: bug
priority: P2
labels: testing, coverage

Complex Docker management code in plugins/docker_manager.py has no test coverage.

**Fix:** Create tests/test_docker_manager.py

## Missing Integration Tests
type: improvement
priority: P2
labels: testing, integration

All tests are unit tests. No integration tests verify full flow from CLI to adapter to result.

**Fix:** Create tests/test_integration.py

## AI Slop - Verbose Docstrings
type: improvement
priority: P3
labels: code-quality, documentation

Overly verbose docstrings with redundant information throughout codebase.

**Fix:** Single-line docstrings for simple functions, move examples to docs

## Content Hashing Never Used - YAGNI
type: improvement
priority: P3
labels: over-engineering, yagni

Complex deterministic hashing in evaluation.py:313-343 that's never used by any code.

**Fix:** Remove until actually needed

## Factory Functions Unnecessary
type: improvement
priority: P3
labels: over-engineering, simplicity

Factory functions that just call constructors add indirection without value.

**Fix:** Use constructors directly

## _builtin_list Workaround - Naming Conflict
type: improvement
priority: P3
labels: code-quality, naming

cli.py stores builtin list because click group shadows it. Code smell.

**Fix:** Rename click group

## Unused Import - Verdict in Standalone
type: bug
priority: P3
labels: code-quality, dead-code

standalone.py imports Verdict but never uses it.

**Fix:** Remove unused import
