# SystemEval Services

Business logic services separated from the CLI layer.

## TestRunner

The `TestRunner` service provides programmatic access to test execution, independent of the CLI.

### Usage

```python
from systemeval.services import TestRunner, TestRunnerConfig

# From YAML config
config = TestRunnerConfig.from_yaml("systemeval.yaml")
runner = TestRunner(config)

# Run tests (auto-selects mode)
result = runner.run(category="unit")

# Or explicitly:
result = runner.run_adapter_tests(category="unit")
result = runner.run_browser_tests()
result = runner.run_with_environment(env_name="backend")
result = runner.run_multi_project()

# Check result
if result.success:
    print(f"All tests passed: {result.test_result.passed}")
else:
    print(f"Tests failed: {result.test_result.failed}")
```

### Programmatic Configuration

```python
from pathlib import Path
from systemeval.services import TestRunner, TestRunnerConfig

config = TestRunnerConfig(
    project_root=Path("/my/project"),
    adapter="pytest",
    parallel=True,
    coverage=True,
    verbose=True,
)

runner = TestRunner(config)
result = runner.run_adapter_tests()
```

### Progress Callbacks

```python
from systemeval.services import TestRunner, TestRunnerConfig

class MyProgress:
    def on_start(self, message: str) -> None:
        print(f"Starting: {message}")

    def on_progress(self, message: str) -> None:
        print(f"Progress: {message}")

    def on_complete(self, message: str, success: bool) -> None:
        print(f"Done: {message} (success={success})")

runner = TestRunner(config, progress=MyProgress())
result = runner.run()
```

### RunResult

The `RunResult` wraps `TestResult` with additional context:

```python
result = runner.run()

# Core result
result.test_result.passed    # Number of passed tests
result.test_result.failed    # Number of failed tests
result.test_result.verdict   # Verdict enum (PASS, FAIL, ERROR)

# Context
result.mode         # "adapter", "browser", "environment", "multi-project"
result.duration     # Total execution time
result.environment  # Environment name if applicable
result.subprojects  # SubprojectResults for multi-project mode

# Convenience
result.success      # True if verdict is PASS
result.exit_code    # 0 for pass, 1 for fail, 2 for error
```

## Design Principles

1. **CLI Independence**: Services contain no presentation logic (no console.print)
2. **Testability**: All dependencies are injectable
3. **Progress Reporting**: Optional callbacks for UI integration
4. **Error Handling**: Returns results, never raises for expected failures
