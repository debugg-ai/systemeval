# E2E Test Generation Provider Interfaces

## Overview

This module defines provider-agnostic interfaces for E2E test generation following strict architectural principles:

1. **No provider lock-in**: Interfaces are true contracts that any E2E provider can implement
2. **No magic values**: All configuration via explicit parameters
3. **No config discovery**: No env var sniffing, no cwd searching
4. **No module side effects**: Nothing runs at import
5. **No string dispatch**: Registry returns instances, not strings

## Architecture

### Core Protocols

**E2EProvider Protocol** - Contract for E2E test generation providers
```python
class E2EProvider(Protocol):
    def generate_tests(changes: ChangeSet, config: E2EConfig) -> GenerationResult
    def get_status(run_id: str) -> StatusResult
    def download_artifacts(run_id: str, output_dir: Path) -> ArtifactResult
    def validate_config(config: E2EConfig) -> ValidationResult
```

**E2EOrchestrator Protocol** - Coordinates the full E2E flow
```python
class E2EOrchestrator(Protocol):
    def analyze_changes(repo_path: Path, base_ref: str, head_ref: str) -> ChangeSet
    def run_e2e_flow(changes: ChangeSet, config: E2EConfig) -> E2EResult
    def await_completion(run_id: str, timeout: int) -> CompletionResult
```

### Type System

All data structures use dataclasses with explicit validation:

- **ChangeSet**: Collection of code changes from git diff
- **Change**: Individual file change (added, modified, deleted, renamed)
- **E2EConfig**: Complete configuration for test generation
- **GenerationResult**: Result of initiating generation
- **StatusResult**: Current status of generation run
- **ArtifactResult**: Downloaded test files and metadata
- **CompletionResult**: Final outcome after polling
- **E2EResult**: Complete orchestration result

### Provider Registry

Registry stores **provider instances**, not classes or strings:

```python
# Create provider with explicit config
provider = SurferProvider(
    api_key="sk-...",
    api_base_url="https://api.surfer.com"
)

# Register instance
register_provider("surfer", provider)

# Get instance (type-safe)
provider = get_provider("surfer")  # Returns E2EProvider instance
```

## Usage Examples

### Basic Usage

```python
from pathlib import Path
from systemeval.e2e import (
    E2EConfig,
    BasicE2EOrchestrator,
    MockE2EProvider,
)

# 1. Create provider instance (explicit config, no env vars)
provider = MockE2EProvider(
    api_key="sk-test-key-12345",
    api_base_url="https://api.example.com",
)

# 2. Create orchestrator
orchestrator = BasicE2EOrchestrator(provider, poll_interval=5)

# 3. Analyze changes
changes = orchestrator.analyze_changes(
    repo_path=Path("/path/to/repo"),
    base_ref="main",
    head_ref="feature-branch",
)

# 4. Configure generation (all explicit parameters)
config = E2EConfig(
    provider_name="mock",
    project_root=Path("/path/to/repo"),
    project_url="http://localhost:3000",
    project_slug="my-project",
    test_framework="playwright",
    programming_language="typescript",
    timeout_seconds=300,
)

# 5. Run E2E flow
result = orchestrator.run_e2e_flow(changes, config)

# 6. Check results
if result.success:
    print(f"Generated {len(result.artifacts.test_files)} test files")
    for test_file in result.artifacts.test_files:
        print(f"  - {test_file}")
else:
    print(f"Failed: {result.error}")
```

### Provider Registration

```python
from systemeval.e2e import register_provider, get_provider

# Register custom provider
custom_provider = MyCustomProvider(api_key="...")
register_provider("custom", custom_provider)

# Use registered provider
provider = get_provider("custom")
result = provider.generate_tests(changes, config)
```

### Direct Provider Usage

```python
# Can use provider directly without orchestrator
provider = MockE2EProvider(api_key="...", api_base_url="...")

# 1. Validate config
validation = provider.validate_config(config)
if not validation.valid:
    print("Errors:", validation.errors)

# 2. Generate tests
generation = provider.generate_tests(changes, config)
print(f"Run ID: {generation.run_id}")

# 3. Poll status
while True:
    status = provider.get_status(generation.run_id)
    if status.status == GenerationStatus.COMPLETED:
        break
    time.sleep(5)

# 4. Download artifacts
artifacts = provider.download_artifacts(
    generation.run_id,
    Path("/output/dir")
)
```

## Implementing a Custom Provider

```python
from pathlib import Path
from systemeval.e2e import (
    E2EProvider,
    ChangeSet,
    E2EConfig,
    GenerationResult,
    StatusResult,
    ArtifactResult,
    ValidationResult,
    GenerationStatus,
)

class CustomProvider:
    """Custom E2E provider implementation."""

    def __init__(self, api_key: str, api_base_url: str) -> None:
        self.api_key = api_key
        self.api_base_url = api_base_url

    def generate_tests(
        self, changes: ChangeSet, config: E2EConfig
    ) -> GenerationResult:
        # Submit to your API
        response = self._api_call("/generate", {
            "changes": [c.to_dict() for c in changes.changes],
            "config": config.to_dict(),
        })

        return GenerationResult(
            run_id=response["run_id"],
            status=GenerationStatus.IN_PROGRESS,
            message="Generation started",
        )

    def get_status(self, run_id: str) -> StatusResult:
        # Check status from your API
        response = self._api_call(f"/status/{run_id}")

        return StatusResult(
            run_id=run_id,
            status=GenerationStatus(response["status"]),
            progress_percent=response.get("progress"),
            tests_generated=response.get("tests_generated", 0),
        )

    def download_artifacts(
        self, run_id: str, output_dir: Path
    ) -> ArtifactResult:
        # Download from your API
        files = self._api_call(f"/artifacts/{run_id}")

        test_files = []
        for file_data in files:
            test_file = output_dir / file_data["name"]
            test_file.write_text(file_data["content"])
            test_files.append(test_file)

        return ArtifactResult(
            run_id=run_id,
            output_directory=output_dir,
            test_files=test_files,
            total_tests=len(test_files),
        )

    def validate_config(self, config: E2EConfig) -> ValidationResult:
        errors = []

        if not config.project_url:
            errors.append("project_url is required")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )

    def _api_call(self, path: str, data: dict = None):
        # Your API implementation
        pass

# Register and use
provider = CustomProvider(api_key="...", api_base_url="...")
register_provider("custom", provider)
```

## Design Principles

### 1. No Provider Lock-In

Interfaces are designed as true contracts. Any provider that implements the protocol methods can be used interchangeably:

```python
def run_tests_with_any_provider(provider: E2EProvider, changes, config):
    # Works with any provider implementation
    result = provider.generate_tests(changes, config)
    return result
```

### 2. No Magic Values

Everything is explicitly configured:

```python
# BAD - magic env vars
provider = SurferProvider()  # reads SURFER_API_KEY from env

# GOOD - explicit config
provider = SurferProvider(
    api_key="sk-...",
    api_base_url="https://api.surfer.com"
)
```

### 3. No Config Discovery

No automatic discovery of config files, env vars, or working directory:

```python
# BAD - discovers config
config = E2EConfig.from_env()  # reads from env
config = E2EConfig.discover()  # searches for config files

# GOOD - explicit paths
config = E2EConfig(
    provider_name="surfer",
    project_root=Path("/absolute/path"),
    api_key="sk-...",
    api_base_url="https://...",
)
```

### 4. No Module Side Effects

Nothing happens at import time:

```python
# No auto-registration
# No API calls
# No file system access
# No environment variable reading

import systemeval.e2e  # Safe - does nothing

# Everything is explicit
provider = create_provider()
register_provider("name", provider)
```

### 5. No String Dispatch

Registry returns instances, not strings or classes:

```python
# BAD - string dispatch
provider = get_provider("surfer")  # Returns class name as string
if provider == "surfer":
    result = surfer_generate(...)

# GOOD - instance dispatch
provider = get_provider("surfer")  # Returns E2EProvider instance
result = provider.generate_tests(...)  # Type-safe method call
```

## Testing

The module includes example implementations for testing:

- **MockE2EProvider**: Simulates test generation without real API calls
- **BasicE2EOrchestrator**: Reference orchestrator implementation

Use these for testing your integrations:

```python
def test_orchestration():
    provider = MockE2EProvider(
        api_key="test",
        api_base_url="http://test",
        simulate_delay=False,  # Instant completion
    )

    orchestrator = BasicE2EOrchestrator(provider)
    result = orchestrator.run_e2e_flow(changes, config)

    assert result.success
    assert len(result.artifacts.test_files) > 0
```

## Integration with SystemEval

The E2E interfaces integrate with systemeval's existing patterns:

- Uses `dataclass` like `AdapterConfig`, `TestResult`
- Follows `Protocol` pattern like `BaseAdapter`
- Follows registry pattern like `AdapterRegistry`
- Returns structured results like `EvaluationResult`
- Uses absolute paths like `AdapterConfig.project_root`

### Future Integration Points

1. **CLI Integration**: Add `systemeval e2e generate` command
2. **Adapter Integration**: Create `E2EAdapter` that wraps providers
3. **Pipeline Integration**: Include E2E generation in test pipelines
4. **Evaluation Integration**: Convert `E2EResult` to `EvaluationResult`

## API Reference

See individual module documentation:

- `protocols.py`: Protocol definitions with detailed docstrings
- `types.py`: All data structures and enums
- `registry.py`: Provider registration and lookup
- `examples.py`: Reference implementations and usage examples
