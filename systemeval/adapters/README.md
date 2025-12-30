# Test Framework Adapters

This directory contains framework-agnostic test adapters for systemeval. Each adapter implements the `BaseAdapter` interface to provide unified test discovery and execution across different testing frameworks.

## Architecture

### Base Adapter Interface

All adapters inherit from `BaseAdapter` (`base.py`) which defines:

**Data Structures:**
- `TestItem`: Represents a discovered test with id, name, path, markers, and metadata
- `TestResult`: Contains execution results (passed, failed, errors, skipped, duration, failures)
- `TestFailure`: Detailed failure information for failed tests

**Abstract Methods:**
- `discover()`: Find tests matching filters (category, app, file)
- `execute()`: Run tests and return results
- `get_available_markers()`: List available test markers/categories
- `validate_environment()`: Check if framework is properly configured

### Pytest Adapter

**File:** `pytest_adapter.py`

The pytest adapter provides comprehensive integration with pytest through:

**Features:**
- **Test Discovery**: Uses pytest's collection API via custom plugin
- **Test Execution**: Runs tests via `pytest.main()` with custom result plugin
- **Marker Support**: Filters tests by pytest markers (unit, integration, api, etc.)
- **App/Module Filtering**: Discover tests in specific directories
- **Parallel Execution**: Optional via pytest-xdist
- **Coverage Reporting**: Optional via pytest-cov
- **Django Detection**: Automatically detects and configures Django projects

**Implementation Details:**

1. **PytestCollectPlugin**: Captures test items during collection phase
   - Hooks into `pytest_collection_finish()` to get all collected items
   - Converts pytest Items to framework-agnostic TestItem objects

2. **PytestResultPlugin**: Captures results during execution
   - Hooks into `pytest_sessionstart/finish()` for timing
   - Hooks into `pytest_runtest_logreport()` to track pass/fail/skip
   - Hooks into `pytest_internalerror()` to track errors
   - Builds TestResult with detailed failure information

3. **Django Support**: Auto-detects Django projects
   - Checks for `manage.py`
   - Searches for settings in common locations
   - Sets `DJANGO_SETTINGS_MODULE` if not already set

**Usage Example:**

```python
from systemeval.adapters import get_adapter

# Get pytest adapter for a project
adapter = get_adapter("pytest", "/path/to/project")

# Validate environment
if not adapter.validate_environment():
    print("Project not configured for pytest")

# Discover all unit tests
unit_tests = adapter.discover(category="unit")

# Discover tests in specific app
app_tests = adapter.discover(app="backend/apps/agents/tests")

# Discover specific test file
file_tests = adapter.discover(file="tests/test_models.py")

# Execute tests
result = adapter.execute(
    tests=unit_tests[:10],  # Run first 10 unit tests
    parallel=True,          # Use pytest-xdist
    coverage=True,          # Generate coverage report
    verbose=True,           # Verbose output
    failfast=True,          # Stop on first failure
    timeout=300             # 5 minute timeout
)

# Check results
print(f"Passed: {result.passed}/{result.total}")
print(f"Failed: {result.failed}")
print(f"Duration: {result.duration:.2f}s")
print(f"Exit code: {result.exit_code}")

# Get failure details
for failure in result.failures:
    print(f"Failed: {failure.test_name}")
    print(f"  Message: {failure.message}")
    print(f"  Duration: {failure.duration:.2f}s")
```

## Registry

**File:** `registry.py`

The adapter registry manages available test framework adapters:

```python
from systemeval.adapters import (
    register_adapter,
    get_adapter,
    list_adapters,
    is_registered
)

# List available adapters
print(list_adapters())  # ['pytest']

# Check if adapter exists
if is_registered("pytest"):
    adapter = get_adapter("pytest", "/path/to/project")

# Register custom adapter
from systemeval.adapters import BaseAdapter

class CustomAdapter(BaseAdapter):
    # Implement abstract methods
    pass

register_adapter("custom", CustomAdapter)
```

**Built-in Adapters:**

The registry automatically registers adapters when their dependencies are available:
- `pytest`: Registered if pytest is installed
- `jest`: Not yet implemented

## Adding New Adapters

To add a new test framework adapter:

1. **Create adapter file** (e.g., `jest_adapter.py`)
2. **Implement BaseAdapter**:
   ```python
   from .base import BaseAdapter, TestItem, TestResult

   class JestAdapter(BaseAdapter):
       def __init__(self, project_root: str) -> None:
           super().__init__(project_root)
           # Framework-specific initialization

       def discover(self, category=None, app=None, file=None):
           # Implement test discovery
           pass

       def execute(self, tests=None, **kwargs):
           # Implement test execution
           pass

       def get_available_markers(self):
           # Return available markers/categories
           pass

       def validate_environment(self):
           # Check if framework is configured
           pass
   ```

3. **Register in registry.py**:
   ```python
   def _register_builtin_adapters() -> None:
       # ... existing registrations ...

       try:
           from .jest_adapter import JestAdapter
           register_adapter("jest", JestAdapter)
       except ImportError:
           pass
   ```

4. **Add dependencies to pyproject.toml**:
   ```toml
   [project.optional-dependencies]
   jest = ["jest-runner>=1.0"]
   ```

## Testing Adapters

Each adapter should be tested with:

1. **Environment validation**: Ensure it detects framework configuration
2. **Test discovery**: Verify it finds tests with various filters
3. **Test execution**: Confirm it runs tests and captures results
4. **Marker detection**: Check it identifies available markers
5. **Error handling**: Test behavior with invalid inputs

## Design Principles

1. **Framework Agnostic**: Adapters hide framework-specific details
2. **Standalone**: Adapters work without Django or other dependencies
3. **Extensible**: Easy to add new test frameworks
4. **Type Safe**: Full type hints for all methods
5. **Minimal Dependencies**: Each adapter only requires its framework
6. **Auto-Configuration**: Detect common project structures

## Dependencies

**Core (no adapter):**
- Python >= 3.10

**Pytest Adapter:**
- pytest >= 7.0
- pytest-xdist >= 3.0 (optional, for parallel execution)
- pytest-cov >= 4.0 (optional, for coverage)

**Jest Adapter (future):**
- TBD

## Implementation Notes

### Pytest Specifics

1. **Working Directory**: Adapter changes to project root before running pytest
2. **Plugin System**: Uses pytest's plugin system for collection and result capture
3. **Exit Codes**: Captures pytest exit codes for additional context
4. **Django Setup**: Automatically configures Django if detected
5. **Relative Paths**: Converts absolute paths to project-relative paths

### Future Enhancements

- [ ] Coverage percentage extraction from pytest-cov
- [ ] Support for pytest-timeout plugin
- [ ] Better parsing of pytest markers from pytest.ini
- [ ] Support for pytest parametrize in test discovery
- [ ] Caching of discovery results
- [ ] Support for pytest fixtures in metadata
- [ ] Jest adapter implementation
- [ ] Vitest adapter implementation
