# E2E Configuration Architecture

## Overview

This document describes the E2E configuration and result type system for systemeval. The architecture follows STRICT principles to prevent the configuration drift and magic values that plague typical testing systems.

## Design Principles

### 1. No Config Discovery

**Config must be passed explicitly at startup.**

```python
# ✅ CORRECT - explicit path
config_path = Path("/explicit/path/to/e2e_config.yaml")
with open(config_path) as f:
    raw_config = yaml.safe_load(f)
config = load_e2e_config_from_dict(raw_config)

# ❌ WRONG - searching cwd
config = find_e2e_config()  # NO - where does it look?

# ❌ WRONG - cwd assumptions
config_path = Path("e2e_config.yaml")  # NO - which directory?
```

**Rationale:** Config discovery creates implicit dependencies on working directory, making systems fragile and hard to reason about. Explicit paths make config loading deterministic.

### 2. No Cascading Fallbacks

**No "try this, then that" patterns.**

```python
# ✅ CORRECT - single explicit value
config = E2EConfig(
    provider="debuggai",
    provider_config={
        "api_key": "sk_live_explicit_key",
        "api_url": "https://api.debugg.ai",
    },
    output_dir=Path("/tmp/e2e-output"),
)

# ❌ WRONG - cascading fallbacks
api_key = config.get("api_key") or os.getenv("DEBUGGAI_API_KEY") or "default"

# ❌ WRONG - default URLs
api_url = config.get("api_url", "https://api.debugg.ai")
```

**Rationale:** Fallback chains make it impossible to know which value is being used. Explicit values are required - if missing, fail fast with clear error.

### 3. No Magic Values

**All values explicit in config.**

```python
# ✅ CORRECT - explicit absolute path
output_dir = Path("/tmp/e2e-output")

# ❌ WRONG - relative path (depends on cwd)
output_dir = Path("./output")

# ❌ WRONG - implicit current directory
output_dir = Path.cwd() / "output"
```

**Rationale:** Relative paths, environment variables, and implicit defaults create hidden dependencies. Absolute paths and explicit values make behavior predictable.

### 4. Fail Fast

**Invalid config raises ValueError immediately.**

```python
# This raises ValueError immediately with clear message
try:
    config = E2EConfig(
        provider="debuggai",
        provider_config={"api_key": ""},  # INVALID
        output_dir=Path("./relative"),    # INVALID
    )
except ValueError as e:
    print(f"Config validation failed: {e}")
    # Output: "api_key cannot be empty"
    # Output: "output_dir must be absolute path"
```

**Rationale:** Early validation prevents runtime surprises. Clear error messages guide users to fix config issues immediately.

## Architecture Components

### Configuration Models

```
e2e_config.py
├── DebuggAIProviderConfig      # DebuggAI-specific settings
├── LocalProviderConfig         # Local provider settings
└── E2EConfig                   # Top-level E2E configuration
```

### Result Types

```
e2e_types.py
├── GenerationResult            # Test generation stage
├── StatusResult                # Status polling stage
├── ArtifactResult             # Artifact collection stage
├── E2EFailure                 # E2E test failure details
└── E2EResult                  # Complete E2E test result
```

### Integration with systemeval

```
types.py (existing)
├── TestResult                 # Unit test results
├── TestFailure                # Unit test failures
└── Verdict                    # PASS/FAIL/ERROR

e2e_types.py (new)
├── E2EResult                  # E2E test results (matches TestResult pattern)
├── E2EFailure                 # E2E test failures (extends TestFailure)
└── Uses Verdict               # Same verdict enum
```

## Usage Examples

### Creating Config Programmatically

```python
from pathlib import Path
from systemeval.e2e_config import E2EConfig

# DebuggAI provider
config = E2EConfig.for_debuggai(
    api_key="sk_live_your_key",
    api_url="https://api.debugg.ai",
    output_dir=Path("/tmp/e2e-output"),
    project_id="my-project",
    timeout_seconds=300,
)

# Local provider
config = E2EConfig.for_local(
    base_url="http://localhost:3000",
    output_dir=Path("/tmp/e2e-output"),
    timeout_seconds=60,
)
```

### Loading Config from YAML

```python
import yaml
from pathlib import Path
from systemeval.e2e_config import load_e2e_config_from_dict

# Caller explicitly reads config file
config_path = Path("/explicit/path/to/e2e_config.yaml")
with open(config_path) as f:
    raw_config = yaml.safe_load(f)

# Then passes to loader
config = load_e2e_config_from_dict(raw_config)
```

### YAML Config Example

```yaml
# e2e_config_debuggai.yaml
provider: debuggai
provider_config:
  api_key: "sk_live_your_key"
  api_url: "https://api.debugg.ai"
  project_id: "my-project"
output_dir: "/tmp/e2e-output"
timeout_seconds: 300
poll_interval_seconds: 5
```

### Creating E2E Results

```python
from systemeval.e2e_types import (
    E2EResult,
    GenerationResult,
    StatusResult,
    ArtifactResult,
)

# Stage 1: Generation
generation = GenerationResult(
    status="success",
    test_run_id="run_abc123",
    message="Test run created",
    duration_seconds=0.5,
)

# Stage 2: Status Polling
status = StatusResult(
    status="completed",
    poll_count=5,
    duration_seconds=45.0,
)

# Stage 3: Artifact Collection
artifacts = ArtifactResult(
    status="success",
    artifacts_collected=["/tmp/screenshot.png"],
    duration_seconds=2.5,
)

# Aggregate result
result = E2EResult(
    test_run_id="run_abc123",
    provider="debuggai",
    passed=8,
    failed=0,
    errors=0,
    skipped=0,
    duration_seconds=48.0,
    generation=generation,
    status=status,
    artifacts=artifacts,
)

# Check verdict
print(result.verdict)  # Verdict.PASS
print(result.to_dict())  # JSON serializable
```

## Verdict Logic

E2EResult verdict is computed based on stage results and test counts:

```python
@property
def verdict(self) -> Verdict:
    # ERROR: If any stage failed to complete
    if self.generation and not self.generation.is_success:
        return Verdict.ERROR

    if self.status:
        if self.status.timeout_exceeded:
            return Verdict.ERROR
        if not self.status.is_terminal:
            return Verdict.ERROR
        if self.status.status == "error":
            return Verdict.ERROR

    if self.exit_code == 2:
        return Verdict.ERROR

    # ERROR: No tests run
    if self.total == 0:
        return Verdict.ERROR

    # FAIL: Tests ran but some failed
    if self.failed > 0 or self.errors > 0:
        return Verdict.FAIL

    # PASS: All tests passed
    return Verdict.PASS
```

## Validation Rules

### DebuggAIProviderConfig

- `api_key`: Required, non-empty string
- `api_url`: Required, must start with `http://` or `https://`
- `project_id`: Optional, non-empty if provided

### LocalProviderConfig

- `base_url`: Required, must start with `http://` or `https://`
- `timeout_seconds`: Integer, 1-600 seconds

### E2EConfig

- `provider`: Must be `"debuggai"` or `"local"`
- `provider_config`: Must be non-empty dict, validated against provider model
- `output_dir`: Must be absolute path (no relative paths)
- `timeout_seconds`: Integer, 1-3600 seconds
- `poll_interval_seconds`: Integer, 1-60 seconds

## Comparison with Legacy Patterns

### ❌ Legacy Pattern (systemeval's SurferConfig)

```python
class SurferConfig(BaseModel):
    api_key: Optional[str] = Field(
        default=None,
        description="DebuggAI API key (or use DEBUGGAI_API_KEY env var)"
    )
    api_base_url: str = Field(
        default="https://api.debugg.ai",  # MAGIC DEFAULT
        description="DebuggAI API base URL"
    )
```

**Problems:**
- Environment variable fallback (implicit)
- Default URL (magic value)
- Unclear which value is actually used

### ✅ New Pattern (E2EConfig)

```python
class DebuggAIProviderConfig(BaseModel):
    api_key: str = Field(
        ...,  # REQUIRED - no default
        description="DebuggAI API key (explicit, NOT from env var)",
        min_length=1,
    )
    api_url: str = Field(
        ...,  # REQUIRED - no default
        description="DebuggAI API base URL (explicit, no defaults)",
        min_length=1,
    )
```

**Benefits:**
- No environment variables
- No default values
- Validation enforces non-empty
- Clear error if missing

## File Structure

```
systemeval/
├── systemeval/
│   ├── e2e_config.py           # E2E configuration models
│   ├── e2e_types.py            # E2E result types
│   ├── config.py               # Existing systemeval config
│   └── types.py                # Existing TestResult types
├── examples/
│   ├── e2e_config_debuggai.yaml    # DebuggAI config example
│   ├── e2e_config_local.yaml       # Local config example
│   └── e2e_usage_example.py        # Python usage examples
└── tests/
    ├── test_e2e_config.py      # Config model tests
    └── test_e2e_types.py       # Result type tests
```

## Testing

### Run Config Tests

```bash
pytest tests/test_e2e_config.py -v
```

### Run Type Tests

```bash
pytest tests/test_e2e_types.py -v
```

### Run Usage Examples

```bash
python examples/e2e_usage_example.py
```

## Integration Points

### With systemeval CLI

Future CLI integration would look like:

```bash
# Pass explicit config path
systemeval e2e --config /path/to/e2e_config.yaml

# NOT this (no discovery):
# systemeval e2e  # NO - where's the config?
```

### With E2E Adapters

E2E adapters (DebuggAI Surfer, etc) accept E2EConfig:

```python
from systemeval.e2e_config import E2EConfig
from systemeval.adapters.e2e_runner import E2ERunner

config = E2EConfig.for_debuggai(
    api_key="sk_live_key",
    api_url="https://api.debugg.ai",
    output_dir=Path("/tmp/e2e"),
)

runner = E2ERunner(config)
result = runner.run()  # Returns E2EResult

print(result.verdict)  # PASS/FAIL/ERROR
```

## Migration from Legacy Configs

If migrating from legacy SurferConfig:

```python
# Legacy (implicit values)
surfer_config = SurferConfig(
    project_slug="my-project",
    # api_key from env var DEBUGGAI_API_KEY
    # api_base_url defaults to "https://api.debugg.ai"
)

# New (explicit values)
e2e_config = E2EConfig.for_debuggai(
    api_key=os.environ["DEBUGGAI_API_KEY"],  # Explicit
    api_url="https://api.debugg.ai",         # Explicit
    output_dir=Path("/tmp/e2e-output"),      # Explicit
    project_id="my-project",
)
```

**Key changes:**
1. Caller explicitly reads env var (no implicit fallback)
2. All URLs must be passed explicitly (no defaults)
3. All paths must be absolute (no cwd assumptions)

## FAQ

### Why no environment variable support?

Environment variables create implicit dependencies that are hard to trace. If a value is needed, it should be explicitly read by the caller and passed to the config. This makes the data flow clear.

### Why no default values for URLs?

Default values become magic constants that change behavior implicitly. By requiring explicit values, we ensure the config is self-documenting and the behavior is deterministic.

### Why require absolute paths?

Relative paths depend on working directory, which varies by execution context. Absolute paths are deterministic regardless of where code is run.

### Why not use find_config() like systemeval?

systemeval's find_config() searches up the directory tree, which works for project-local configs but creates implicit dependencies. E2E configs often involve external services and should be explicitly provided, not discovered.

### Can I use relative paths if I resolve them first?

Yes, but the resolved absolute path must be passed to E2EConfig:

```python
# OK - resolve relative path first
relative = Path("./output")
absolute = relative.resolve()
config = E2EConfig(..., output_dir=absolute)

# NOT OK - pass relative path
config = E2EConfig(..., output_dir=relative)  # ValueError
```

## References

- Pydantic validation: https://docs.pydantic.dev/latest/concepts/validators/
- systemeval config patterns: `systemeval/config.py`
- systemeval result patterns: `systemeval/types.py`
- Field validators: `@field_validator` decorator usage
