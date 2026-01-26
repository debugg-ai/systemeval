# E2E Provider Architecture

## Design Principles

This module follows **5 strict architectural principles** that prevent common anti-patterns:

### 1. No Provider Lock-In
Interfaces are true contracts - any implementation can be swapped without code changes.

**Anti-pattern**: Tightly coupling to a specific provider's API
```python
# BAD - direct coupling
from surfer import SurferClient
client = SurferClient()
result = client.generate_e2e_tests(...)  # Can't swap providers
```

**Good pattern**: Protocol-based abstraction
```python
# GOOD - any provider works
provider: E2EProvider = get_provider("surfer")  # or "custom", etc.
result = provider.generate_tests(...)  # Works with any implementation
```

### 2. No Magic Values
All configuration is explicit - no hidden defaults or environment variable discovery.

**Anti-pattern**: Reading environment variables automatically
```python
# BAD - magic env vars
class SurferProvider:
    def __init__(self):
        self.api_key = os.getenv("SURFER_API_KEY")  # Magic!
        self.base_url = os.getenv("SURFER_BASE_URL", "https://api.surfer.com")
```

**Good pattern**: Explicit parameters
```python
# GOOD - explicit config
provider = SurferProvider(
    api_key="sk-...",           # Explicit
    api_base_url="https://..."  # No defaults from env
)
```

### 3. No Config Discovery
No automatic searching for config files or working directory detection.

**Anti-pattern**: Automatic config file discovery
```python
# BAD - discovers config
class E2EConfig:
    @classmethod
    def discover(cls):
        # Searches for .e2econfig, e2e.json, etc.
        for path in possible_paths:
            if path.exists():
                return cls.from_file(path)
```

**Good pattern**: Explicit paths
```python
# GOOD - explicit paths
config = E2EConfig(
    provider_name="surfer",
    project_root=Path("/absolute/path"),  # Explicit
    api_key="sk-...",                     # Explicit
)
```

### 4. No Module Side Effects
Nothing runs at import time - no API calls, no file system access, no registration.

**Anti-pattern**: Auto-registration at import
```python
# BAD - side effects at import
# In surfer_provider.py:
provider = SurferProvider.from_env()  # Runs at import!
register_provider("surfer", provider)  # Side effect!

# Just importing the module does stuff:
import surfer_provider  # Already registered!
```

**Good pattern**: Explicit registration
```python
# GOOD - explicit setup
import systemeval.e2e  # Does nothing

# Later, when you want to use it:
provider = SurferProvider(api_key="...", api_base_url="...")
register_provider("surfer", provider)
```

### 5. No String Dispatch
Registry returns instances, not strings or classes - enables type safety.

**Anti-pattern**: String-based dispatch
```python
# BAD - string dispatch
provider_name = get_provider("surfer")  # Returns "surfer" string

if provider_name == "surfer":
    result = surfer_generate(...)
elif provider_name == "custom":
    result = custom_generate(...)
# Brittle, no type safety
```

**Good pattern**: Instance-based dispatch
```python
# GOOD - instance dispatch
provider = get_provider("surfer")  # Returns E2EProvider instance
result = provider.generate_tests(...)  # Type-safe, works with any provider
```

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                      Application Layer                      │
│  (CLI commands, automation scripts, CI/CD integrations)     │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator Layer                        │
│  • E2EOrchestrator protocol                                 │
│  • Coordinates: git analysis → generation → polling → download│
│  • Example: BasicE2EOrchestrator                            │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     Provider Layer                          │
│  • E2EProvider protocol                                     │
│  • Methods: generate_tests, get_status, download_artifacts  │
│  • Implementations: SurferProvider, CustomProvider, etc.    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     Registry Layer                          │
│  • E2EProviderRegistry                                      │
│  • Instance-based (not string-based)                        │
│  • Type-safe lookup                                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                      Type Layer                             │
│  • ChangeSet, Change, E2EConfig                             │
│  • GenerationResult, StatusResult, ArtifactResult           │
│  • All dataclasses with validation                          │
└─────────────────────────────────────────────────────────────┘
```

## Protocol Definitions

### E2EProvider Protocol

The core contract for test generation providers:

```python
class E2EProvider(Protocol):
    """Contract for E2E test generation."""

    def generate_tests(
        self, changes: ChangeSet, config: E2EConfig
    ) -> GenerationResult:
        """Initiate test generation (non-blocking)."""

    def get_status(self, run_id: str) -> StatusResult:
        """Check generation status."""

    def download_artifacts(
        self, run_id: str, output_dir: Path
    ) -> ArtifactResult:
        """Download generated tests."""

    def validate_config(self, config: E2EConfig) -> ValidationResult:
        """Validate configuration before generation."""
```

**Key characteristics**:
- Protocol (not base class) - no inheritance required
- Pure interface - no implementation details
- Explicit parameters - no hidden state
- Type-safe - all inputs/outputs have concrete types

### E2EOrchestrator Protocol

Coordinates the full workflow:

```python
class E2EOrchestrator(Protocol):
    """Orchestrates E2E generation workflow."""

    def analyze_changes(
        self, repo_path: Path, base_ref: str, head_ref: str
    ) -> ChangeSet:
        """Analyze git changes."""

    def run_e2e_flow(
        self, changes: ChangeSet, config: E2EConfig
    ) -> E2EResult:
        """Run complete E2E flow (blocking)."""

    def await_completion(
        self, run_id: str, timeout: int
    ) -> CompletionResult:
        """Poll until completion or timeout."""
```

**Key characteristics**:
- Composes a provider with analysis and polling logic
- Blocking operations (waits for completion)
- Handles timeouts and retries
- Returns comprehensive results

## Type System

All data structures use dataclasses with explicit validation:

### Input Types

**ChangeSet** - Code changes to generate tests for
```python
@dataclass
class ChangeSet:
    base_ref: str              # Git base reference
    head_ref: str              # Git head reference
    changes: List[Change]      # Individual file changes
    repository_root: Path      # Absolute path (validated)
    timestamp: str             # ISO 8601
    metadata: Dict[str, Any]   # Additional context
```

**Change** - Single file change
```python
@dataclass
class Change:
    file_path: str             # Relative from repo root
    change_type: ChangeType    # ADDED, MODIFIED, DELETED, RENAMED
    old_path: Optional[str]    # Previous path if renamed
    additions: int             # Lines added (≥0)
    deletions: int             # Lines deleted (≥0)
    diff: Optional[str]        # Full diff content
    metadata: Dict[str, Any]   # Additional data
```

**E2EConfig** - Complete configuration
```python
@dataclass
class E2EConfig:
    provider_name: str         # Provider identifier
    project_root: Path         # Absolute path (validated)
    api_key: Optional[str]     # Explicit (not from env)
    api_base_url: Optional[str]  # Explicit (not from env)
    project_slug: Optional[str]  # Project identifier
    project_url: Optional[str]   # App URL
    test_framework: str        # playwright, cypress, selenium
    programming_language: str  # typescript, javascript, python
    output_directory: Optional[Path]  # Where to write tests
    timeout_seconds: int       # Max wait time (>0)
    max_tests: Optional[int]   # Max tests to generate (>0)
    parallel: bool             # Parallel generation
    extra: Dict[str, Any]      # Provider-specific options
```

### Output Types

**GenerationResult** - Initial generation response
```python
@dataclass
class GenerationResult:
    run_id: str                # Unique identifier
    status: GenerationStatus   # PENDING, IN_PROGRESS, etc.
    message: Optional[str]     # Human-readable status
    started_at: str            # ISO 8601
    metadata: Dict[str, Any]   # Provider-specific data
```

**StatusResult** - Current generation status
```python
@dataclass
class StatusResult:
    run_id: str                # Unique identifier
    status: GenerationStatus   # Current status
    message: Optional[str]     # Status message
    progress_percent: Optional[float]  # 0-100 if available
    tests_generated: int       # Count so far
    completed_at: Optional[str]  # ISO 8601 if done
    error: Optional[str]       # Error message if failed
    metadata: Dict[str, Any]   # Provider-specific data
```

**ArtifactResult** - Downloaded test files
```python
@dataclass
class ArtifactResult:
    run_id: str                # Unique identifier
    output_directory: Path     # Where files were written
    test_files: List[Path]     # Generated test file paths
    total_tests: int           # Test count
    total_size_bytes: int      # Total size
    metadata: Dict[str, Any]   # Provider-specific data
```

**E2EResult** - Complete orchestration result
```python
@dataclass
class E2EResult:
    changeset: ChangeSet       # Input changes
    config: E2EConfig          # Configuration used
    generation: GenerationResult  # Initial response
    completion: CompletionResult  # Final status
    artifacts: Optional[ArtifactResult]  # Files (if successful)
    started_at: str            # ISO 8601
    completed_at: Optional[str]  # ISO 8601
    total_duration_seconds: float  # Total time
    success: bool              # Overall success
    error: Optional[str]       # Error message
    warnings: List[str]        # Non-blocking warnings
    metadata: Dict[str, Any]   # Orchestrator metadata
```

## Data Flow

### Complete E2E Flow

```
┌────────────┐
│ Git Repo   │
└──────┬─────┘
       │ analyze_changes(repo_path, base_ref, head_ref)
       ▼
┌────────────────┐
│ ChangeSet      │  (base_ref, head_ref, changes: [Change, ...])
└──────┬─────────┘
       │ + E2EConfig
       ▼
┌────────────────────┐
│ Orchestrator       │
│ run_e2e_flow()     │
└──────┬─────────────┘
       │
       ├─► validate_config() ──► ValidationResult
       │
       ├─► generate_tests() ──► GenerationResult (run_id)
       │
       ├─► await_completion() ──► CompletionResult
       │   │
       │   └─► (polling loop)
       │       ├─► get_status() ──► StatusResult
       │       ├─► get_status() ──► StatusResult
       │       └─► get_status() ──► StatusResult (COMPLETED)
       │
       └─► download_artifacts() ──► ArtifactResult
           │
           └─► test_file_1.spec.ts
               test_file_2.spec.ts
               test_file_3.spec.ts
```

### Provider Implementation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Provider Implementation                   │
│                                                              │
│  generate_tests()                                            │
│    1. Validate inputs                                        │
│    2. Prepare API request payload                            │
│    3. POST /generate → { run_id: "..." }                     │
│    4. Return GenerationResult                                │
│                                                              │
│  get_status()                                                │
│    1. GET /status/{run_id} → { status, progress, ... }      │
│    2. Return StatusResult                                    │
│                                                              │
│  download_artifacts()                                        │
│    1. GET /artifacts/{run_id} → [file1, file2, ...]         │
│    2. Write files to output_directory                        │
│    3. Return ArtifactResult with file paths                  │
│                                                              │
│  validate_config()                                           │
│    1. Check required fields                                  │
│    2. Validate API credentials                               │
│    3. Check framework/language support                       │
│    4. Return ValidationResult                                │
└─────────────────────────────────────────────────────────────┘
```

## Registry Pattern

The registry stores **provider instances**, not classes or strings:

```python
# Traditional pattern (string dispatch)
registry["surfer"] = SurferProvider  # Class
provider = registry["surfer"]()      # Instantiate
result = provider.generate_tests()   # Call method

# Our pattern (instance dispatch)
registry["surfer"] = SurferProvider(api_key="...", base_url="...")  # Instance
provider = registry["surfer"]        # Get instance
result = provider.generate_tests()   # Call method (type-safe)
```

**Why instance-based?**
1. **No magic**: Configuration passed explicitly at registration
2. **Type safety**: Registry returns `E2EProvider` instances
3. **Testability**: Easy to inject mock instances
4. **Immutability**: Can't accidentally reconfigure after registration

## Integration with SystemEval

The E2E interfaces follow systemeval's existing patterns:

| Pattern | E2E Implementation | SystemEval Example |
|---------|-------------------|-------------------|
| Dataclasses | `ChangeSet`, `E2EConfig` | `AdapterConfig`, `TestResult` |
| Protocols | `E2EProvider`, `E2EOrchestrator` | `BaseAdapter` (ABC) |
| Registry | `E2EProviderRegistry` | `AdapterRegistry` |
| Validation | `__post_init__` checks | `AdapterConfig.__post_init__` |
| Absolute paths | `project_root`, `repository_root` | `AdapterConfig.project_root` |
| Structured results | `E2EResult.to_dict()` | `TestResult.to_dict()` |

### Future Integration

**CLI Command**
```bash
systemeval e2e generate \
  --provider surfer \
  --base-ref main \
  --head-ref feature-branch \
  --project-url http://localhost:3000
```

**Adapter Wrapper**
```python
class E2EAdapter(BaseAdapter):
    """Wrap E2E provider as SystemEval adapter."""

    def __init__(self, config: AdapterConfig, provider: E2EProvider):
        super().__init__(config)
        self.provider = provider

    def discover(self, **kwargs) -> List[TestItem]:
        # Convert E2E artifacts to TestItems
        pass

    def execute(self, **kwargs) -> TestResult:
        # Run E2E generation and convert to TestResult
        pass
```

**Pipeline Integration**
```python
# In pipeline config
{
    "e2e_generation": {
        "provider": "surfer",
        "on_change": ["src/**/*.py", "api/**/*.ts"],
        "config": {
            "test_framework": "playwright",
            "programming_language": "typescript"
        }
    }
}
```

## Testing Strategy

### Unit Tests
- Type validation (ChangeSet, E2EConfig)
- Registry operations (register, get, list)
- Provider implementations (MockE2EProvider)
- Orchestrator logic (BasicE2EOrchestrator)

### Integration Tests
- Complete workflow (changes → generation → download)
- Registry integration (register → get → use)
- Error handling (validation failures, timeouts)

### Mock Provider
```python
provider = MockE2EProvider(
    api_key="test",
    api_base_url="http://test",
    simulate_delay=False,  # Instant completion for tests
)
```

Benefits:
- No external dependencies
- Deterministic behavior
- Fast test execution
- Full coverage of interface

## Extension Points

### Custom Provider
Implement the 4 protocol methods:
```python
class CustomProvider:
    def generate_tests(self, changes, config) -> GenerationResult: ...
    def get_status(self, run_id) -> StatusResult: ...
    def download_artifacts(self, run_id, output_dir) -> ArtifactResult: ...
    def validate_config(self, config) -> ValidationResult: ...
```

### Custom Orchestrator
Implement the 3 protocol methods:
```python
class CustomOrchestrator:
    def analyze_changes(self, repo_path, base_ref, head_ref) -> ChangeSet: ...
    def run_e2e_flow(self, changes, config) -> E2EResult: ...
    def await_completion(self, run_id, timeout) -> CompletionResult: ...
```

### Custom Types
Extend with provider-specific metadata:
```python
config = E2EConfig(
    ...,
    extra={
        "custom_option": "value",
        "another_option": 123,
    }
)

# Access in provider
custom_value = config.get("custom_option")
```

## Anti-Patterns to Avoid

### ❌ Environment Variable Discovery
```python
# BAD
api_key = os.getenv("E2E_API_KEY")  # Magic!
```

### ❌ Config File Discovery
```python
# BAD
config = E2EConfig.discover()  # Searches filesystem
```

### ❌ Relative Paths
```python
# BAD
config = E2EConfig(project_root=".")  # Relative!
```

### ❌ Import Side Effects
```python
# BAD
# In __init__.py:
register_all_providers()  # Runs at import!
```

### ❌ String Dispatch
```python
# BAD
provider_type = get_provider("surfer")  # Returns string
if provider_type == "surfer":
    result = surfer_api.generate(...)
```

### ✅ Correct Patterns

```python
# GOOD - explicit configuration
provider = SurferProvider(
    api_key="sk-explicit-key",
    api_base_url="https://explicit-url.com"
)

# GOOD - absolute paths
config = E2EConfig(
    project_root=Path("/absolute/path")
)

# GOOD - explicit registration
register_provider("surfer", provider)

# GOOD - instance dispatch
provider = get_provider("surfer")  # Returns E2EProvider instance
result = provider.generate_tests(...)  # Type-safe
```

## Summary

The E2E provider interfaces provide:

1. **Provider Independence**: Any E2E provider can implement the protocol
2. **Explicit Configuration**: No magic, no discovery, no env vars
3. **Type Safety**: Protocol-based with concrete types
4. **Testability**: Mock implementations for testing
5. **Extensibility**: Easy to add custom providers/orchestrators
6. **Integration**: Follows systemeval's existing patterns

The architecture prioritizes **clarity over convenience**, **explicitness over magic**, and **type safety over flexibility**.
