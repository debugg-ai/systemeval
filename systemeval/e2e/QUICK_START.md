# E2E Provider Quick Start

## 30-Second Overview

E2E provider interfaces for generating end-to-end tests from code changes.

**Key principle**: No magic - everything explicit.

## Installation

The E2E module is part of systemeval:

```python
from systemeval.e2e import (
    E2EProvider,           # Protocol
    E2EOrchestrator,       # Protocol
    E2EConfig,             # Configuration
    MockE2EProvider,       # Example implementation
    BasicE2EOrchestrator,  # Example orchestrator
)
```

## Basic Usage

### Step 1: Create Provider

```python
from systemeval.e2e import MockE2EProvider

# Create provider with explicit config (no env vars!)
provider = MockE2EProvider(
    api_key="sk-your-key",
    api_base_url="https://api.example.com",
)
```

### Step 2: Create Orchestrator

```python
from systemeval.e2e import BasicE2EOrchestrator

orchestrator = BasicE2EOrchestrator(provider)
```

### Step 3: Analyze Changes

```python
from pathlib import Path

changes = orchestrator.analyze_changes(
    repo_path=Path("/absolute/path/to/repo"),
    base_ref="main",
    head_ref="feature-branch",
)

print(f"Found {changes.total_changes} changes")
```

### Step 4: Configure Generation

```python
from systemeval.e2e import E2EConfig

config = E2EConfig(
    provider_name="mock",
    project_root=Path("/absolute/path/to/project"),
    project_url="http://localhost:3000",
    test_framework="playwright",
    programming_language="typescript",
)
```

### Step 5: Generate Tests

```python
result = orchestrator.run_e2e_flow(changes, config)

if result.success:
    print(f"✓ Generated {len(result.artifacts.test_files)} test files:")
    for test_file in result.artifacts.test_files:
        print(f"  - {test_file}")
else:
    print(f"✗ Failed: {result.error}")
```

## Complete Example

```python
from pathlib import Path
from systemeval.e2e import (
    E2EConfig,
    MockE2EProvider,
    BasicE2EOrchestrator,
)

# 1. Create provider
provider = MockE2EProvider(
    api_key="sk-test",
    api_base_url="http://test.com",
    simulate_delay=False,
)

# 2. Create orchestrator
orchestrator = BasicE2EOrchestrator(provider)

# 3. Analyze changes
changes = orchestrator.analyze_changes(
    repo_path=Path.cwd(),
    base_ref="main",
    head_ref="HEAD",
)

# 4. Configure
config = E2EConfig(
    provider_name="mock",
    project_root=Path.cwd(),
    project_url="http://localhost:3000",
    test_framework="playwright",
    programming_language="typescript",
)

# 5. Run
result = orchestrator.run_e2e_flow(changes, config)

# 6. Check results
if result.success:
    for test_file in result.artifacts.test_files:
        print(f"Generated: {test_file}")
```

## Using the Registry

```python
from systemeval.e2e import register_provider, get_provider

# Register once
provider = MockE2EProvider(api_key="...", api_base_url="...")
register_provider("mock", provider)

# Use anywhere
provider = get_provider("mock")
result = provider.generate_tests(changes, config)
```

## Direct Provider Usage

Without orchestrator:

```python
# 1. Validate config
validation = provider.validate_config(config)
if not validation.valid:
    print("Errors:", validation.errors)
    exit(1)

# 2. Generate tests
generation = provider.generate_tests(changes, config)
print(f"Started: {generation.run_id}")

# 3. Poll status
import time
while True:
    status = provider.get_status(generation.run_id)
    if status.status == GenerationStatus.COMPLETED:
        break
    print(f"Progress: {status.progress_percent}%")
    time.sleep(5)

# 4. Download
output_dir = Path("/tmp/tests")
output_dir.mkdir(exist_ok=True)
artifacts = provider.download_artifacts(generation.run_id, output_dir)
print(f"Downloaded {len(artifacts.test_files)} files")
```

## Creating a Custom Provider

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

class MyProvider:
    """Custom E2E provider."""

    def __init__(self, api_key: str, api_base_url: str):
        self.api_key = api_key
        self.api_base_url = api_base_url

    def generate_tests(
        self, changes: ChangeSet, config: E2EConfig
    ) -> GenerationResult:
        # Submit to your API
        response = self._post("/generate", {
            "changes": [c.to_dict() for c in changes.changes],
        })
        return GenerationResult(
            run_id=response["run_id"],
            status=GenerationStatus.IN_PROGRESS,
        )

    def get_status(self, run_id: str) -> StatusResult:
        # Check status
        response = self._get(f"/status/{run_id}")
        return StatusResult(
            run_id=run_id,
            status=GenerationStatus(response["status"]),
            tests_generated=response.get("tests_generated", 0),
        )

    def download_artifacts(
        self, run_id: str, output_dir: Path
    ) -> ArtifactResult:
        # Download files
        files = self._get(f"/artifacts/{run_id}")
        test_files = []
        for file_data in files:
            path = output_dir / file_data["name"]
            path.write_text(file_data["content"])
            test_files.append(path)
        return ArtifactResult(
            run_id=run_id,
            output_directory=output_dir,
            test_files=test_files,
            total_tests=len(test_files),
        )

    def validate_config(self, config: E2EConfig) -> ValidationResult:
        errors = []
        if not config.project_url:
            errors.append("project_url required")
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )

    def _get(self, path: str):
        # HTTP GET implementation
        pass

    def _post(self, path: str, data: dict):
        # HTTP POST implementation
        pass
```

## Common Patterns

### Validation First

```python
validation = provider.validate_config(config)
if not validation.valid:
    for error in validation.errors:
        print(f"ERROR: {error}")
    for warning in validation.warnings:
        print(f"WARNING: {warning}")
    exit(1)
```

### Error Handling

```python
try:
    result = orchestrator.run_e2e_flow(changes, config)
except ValueError as e:
    print(f"Configuration error: {e}")
except TimeoutError as e:
    print(f"Generation timed out: {e}")
except RuntimeError as e:
    print(f"Provider error: {e}")
```

### Progress Monitoring

```python
generation = provider.generate_tests(changes, config)

while True:
    status = provider.get_status(generation.run_id)
    print(f"[{status.status.value}] {status.tests_generated} tests")

    if status.status == GenerationStatus.COMPLETED:
        break
    elif status.status == GenerationStatus.FAILED:
        print(f"Failed: {status.error}")
        break

    time.sleep(5)
```

### Custom Output Directory

```python
config = E2EConfig(
    ...,
    output_directory=Path("/custom/path/to/tests"),
)

# Or relative to project_root
config = E2EConfig(
    project_root=Path("/project"),
    output_directory=Path("tests/e2e"),  # Resolves to /project/tests/e2e
)
```

## Testing

Use `MockE2EProvider` for testing:

```python
def test_my_code():
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

## Type Checking

All interfaces are fully typed:

```python
from systemeval.e2e import E2EProvider

def process_provider(provider: E2EProvider):
    # Type checker knows provider has these methods
    result = provider.generate_tests(changes, config)
    status = provider.get_status(result.run_id)
```

## Next Steps

- Read [README.md](README.md) for detailed API reference
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for design principles
- See [examples.py](examples.py) for reference implementations
- Run tests: `pytest tests/test_e2e_interfaces.py`

## Key Takeaways

1. **No magic**: All config explicit
2. **Absolute paths**: Always use `Path().resolve()`
3. **Protocol-based**: Any implementation works
4. **Type-safe**: Full type hints
5. **Testable**: Mock implementations provided

## Anti-Patterns to Avoid

```python
# ❌ BAD - env vars
api_key = os.getenv("API_KEY")

# ❌ BAD - relative paths
config = E2EConfig(project_root=".")

# ❌ BAD - auto-discovery
config = E2EConfig.discover()

# ✅ GOOD - explicit
provider = Provider(
    api_key="sk-explicit",
    api_base_url="https://explicit",
)
config = E2EConfig(
    project_root=Path(__file__).parent.resolve(),
)
```
