# E2E Configuration Architecture Diagram

## Component Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                     E2E Configuration System                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        Configuration Layer                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐          ┌──────────────────────┐   │
│  │     E2EConfig        │          │  Provider Configs    │   │
│  ├──────────────────────┤          ├──────────────────────┤   │
│  │ - provider           │          │ DebuggAIProvider     │   │
│  │ - provider_config    │────────▶ │ - api_key            │   │
│  │ - output_dir         │          │ - api_url            │   │
│  │ - timeout_seconds    │          │ - project_id         │   │
│  │ - poll_interval      │          └──────────────────────┘   │
│  └──────────────────────┘                     │                │
│           │                                    │                │
│           │                      ┌─────────────┴─────────┐     │
│           │                      │                       │     │
│           │          ┌──────────────────────┐           │     │
│           │          │  LocalProvider       │           │     │
│           │          ├──────────────────────┤           │     │
│           │          │ - base_url           │           │     │
│           │          │ - timeout_seconds    │           │     │
│           │          └──────────────────────┘           │     │
│           │                                              │     │
└───────────┼──────────────────────────────────────────────┼─────┘
            │                                              │
            ▼                                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Execution Layer                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐                                      │
│  │    E2E Runner        │                                      │
│  ├──────────────────────┤                                      │
│  │ run()                │                                      │
│  └──────────────────────┘                                      │
│           │                                                     │
│           │ Executes in stages                                 │
│           ▼                                                     │
│  ┌──────────────────────────────────────────────────────┐     │
│  │                 Stage 1: Generation                   │     │
│  ├──────────────────────────────────────────────────────┤     │
│  │ Submit test specification to provider                │     │
│  │ Returns: GenerationResult                            │     │
│  │   - status: success/error                            │     │
│  │   - test_run_id: str                                 │     │
│  │   - error: Optional[str]                             │     │
│  └──────────────────────────────────────────────────────┘     │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────────────────────┐     │
│  │                Stage 2: Status Polling                │     │
│  ├──────────────────────────────────────────────────────┤     │
│  │ Poll provider for test execution status              │     │
│  │ Returns: StatusResult                                │     │
│  │   - status: pending/running/completed/failed/error   │     │
│  │   - poll_count: int                                  │     │
│  │   - timeout_exceeded: bool                           │     │
│  └──────────────────────────────────────────────────────┘     │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────────────────────┐     │
│  │            Stage 3: Artifact Collection               │     │
│  ├──────────────────────────────────────────────────────┤     │
│  │ Download test artifacts (screenshots, videos, etc)   │     │
│  │ Returns: ArtifactResult                              │     │
│  │   - status: success/partial/error                    │     │
│  │   - artifacts_collected: List[str]                   │     │
│  │   - artifacts_failed: List[str]                      │     │
│  └──────────────────────────────────────────────────────┘     │
│           │                                                     │
└───────────┼─────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Result Layer                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐                                      │
│  │     E2EResult        │  (Like TestResult from types.py)     │
│  ├──────────────────────┤                                      │
│  │ Stage Results:       │                                      │
│  │ - generation         │────▶ GenerationResult                │
│  │ - status             │────▶ StatusResult                    │
│  │ - artifacts          │────▶ ArtifactResult                  │
│  │                      │                                      │
│  │ Test Metrics:        │                                      │
│  │ - passed             │                                      │
│  │ - failed             │                                      │
│  │ - errors             │                                      │
│  │ - skipped            │                                      │
│  │ - duration_seconds   │                                      │
│  │                      │                                      │
│  │ Computed:            │                                      │
│  │ - verdict()          │────▶ PASS/FAIL/ERROR (Verdict enum) │
│  │ - total()            │────▶ int                             │
│  │ - to_dict()          │────▶ JSON-serializable dict          │
│  └──────────────────────┘                                      │
│           │                                                     │
│           │ Contains failures                                  │
│           ▼                                                     │
│  ┌──────────────────────┐                                      │
│  │    E2EFailure        │  (Extends TestFailure)               │
│  ├──────────────────────┤                                      │
│  │ Base Fields:         │                                      │
│  │ - test_id            │                                      │
│  │ - test_name          │                                      │
│  │ - message            │                                      │
│  │ - traceback          │                                      │
│  │ - duration           │                                      │
│  │                      │                                      │
│  │ E2E-Specific:        │                                      │
│  │ - screenshot_path    │                                      │
│  │ - video_path         │                                      │
│  │ - trace_path         │                                      │
│  │ - console_logs       │                                      │
│  └──────────────────────┘                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
┌──────────────┐
│ Config File  │ (YAML)
│ (explicit)   │
└──────┬───────┘
       │
       │ load_e2e_config_from_dict()
       ▼
┌──────────────┐
│  E2EConfig   │ (validated)
└──────┬───────┘
       │
       │ pass to runner
       ▼
┌──────────────┐
│ E2E Runner   │
└──────┬───────┘
       │
       │ Stage 1: Generate
       ▼
┌────────────────────┐
│ GenerationResult   │
│ - test_run_id      │
└──────┬─────────────┘
       │
       │ Stage 2: Poll Status
       ▼
┌────────────────────┐
│  StatusResult      │
│ - completed        │
└──────┬─────────────┘
       │
       │ Stage 3: Collect Artifacts
       ▼
┌────────────────────┐
│ ArtifactResult     │
│ - artifacts: [...]  │
└──────┬─────────────┘
       │
       │ Aggregate Results
       ▼
┌────────────────────┐
│   E2EResult        │
│ verdict: PASS      │
│ passed: 8          │
│ failed: 0          │
└──────┬─────────────┘
       │
       │ to_dict()
       ▼
┌────────────────────┐
│  JSON Output       │
│ {verdict: "PASS"}  │
└────────────────────┘
```

## Validation Flow

```
┌────────────────────────────────────────────────────────────────┐
│                   Config Validation (Fail Fast)                │
└────────────────────────────────────────────────────────────────┘

User Input (YAML/Dict)
       │
       │ E2EConfig.__init__()
       ▼
┌────────────────────┐
│ Pydantic Validator │
└──────┬─────────────┘
       │
       ├───▶ Check: provider in ["debuggai", "local"]
       │     ✓ Valid: continue
       │     ✗ Invalid: raise ValueError
       │
       ├───▶ Check: output_dir.is_absolute()
       │     ✓ Absolute: continue
       │     ✗ Relative: raise ValueError("must be absolute path")
       │
       ├───▶ Check: provider_config is dict and non-empty
       │     ✓ Valid: continue
       │     ✗ Invalid: raise ValueError("cannot be empty")
       │
       └───▶ Check: timeout_seconds in range [1, 3600]
             ✓ Valid: continue
             ✗ Invalid: raise ValueError

If all checks pass:
       │
       ▼
┌────────────────────┐
│ Valid E2EConfig    │
│ Ready to use       │
└────────────────────┘
```

## Verdict Computation

```
┌────────────────────────────────────────────────────────────────┐
│                    E2EResult.verdict Property                   │
└────────────────────────────────────────────────────────────────┘

Check Stage Results
       │
       ├───▶ generation.is_success == False?
       │     YES ──▶ return Verdict.ERROR
       │     NO  ──▶ continue
       │
       ├───▶ status.timeout_exceeded == True?
       │     YES ──▶ return Verdict.ERROR
       │     NO  ──▶ continue
       │
       ├───▶ status.is_terminal == False?
       │     YES ──▶ return Verdict.ERROR
       │     NO  ──▶ continue
       │
       ├───▶ status.status == "error"?
       │     YES ──▶ return Verdict.ERROR
       │     NO  ──▶ continue
       │
       ├───▶ artifacts.status == "error"?
       │     YES ──▶ return Verdict.ERROR
       │     NO  ──▶ continue
       │
       └───▶ exit_code == 2?
             YES ──▶ return Verdict.ERROR
             NO  ──▶ continue

Check Test Results
       │
       ├───▶ total == 0?
       │     YES ──▶ return Verdict.ERROR
       │     NO  ──▶ continue
       │
       └───▶ failed > 0 OR errors > 0?
             YES ──▶ return Verdict.FAIL
             NO  ──▶ return Verdict.PASS
```

## Integration with systemeval

```
┌────────────────────────────────────────────────────────────────┐
│                    systemeval Architecture                      │
└────────────────────────────────────────────────────────────────┘

Existing:                          New:
┌──────────────┐                   ┌──────────────┐
│ config.py    │                   │ e2e_config.py│
├──────────────┤                   ├──────────────┤
│ SystemEval   │                   │ E2EConfig    │
│ Config       │                   │              │
│ - adapter    │                   │ - provider   │
│ - test_dir   │                   │ - output_dir │
└──────────────┘                   └──────────────┘
       │                                   │
       │                                   │
       ▼                                   ▼
┌──────────────┐                   ┌──────────────┐
│ types.py     │◀─────────shares────│ e2e_types.py │
├──────────────┤    Verdict enum    ├──────────────┤
│ TestResult   │                    │ E2EResult    │
│ - verdict    │                    │ - verdict    │
│ - passed     │                    │ - passed     │
│ - failed     │                    │ - failed     │
│ - failures   │                    │ - failures   │
│ TestFailure  │                    │ E2EFailure   │
└──────────────┘                   └──────────────┘
       │                                   │
       │                                   │
       ▼                                   ▼
┌──────────────┐                   ┌──────────────┐
│ Adapters     │                   │ E2E Runner   │
├──────────────┤                   ├──────────────┤
│ Pytest       │                   │ DebuggAI     │
│ Jest         │                   │ Local        │
│ Playwright   │                   │ (future)     │
└──────────────┘                   └──────────────┘
```

## File Organization

```
systemeval/
├── systemeval/
│   ├── config.py          ◀─── Existing config (SystemEvalConfig)
│   ├── types.py           ◀─── Existing types (TestResult, Verdict)
│   │
│   ├── e2e_config.py      ◀─── New E2E config (E2EConfig)
│   │   ├── DebuggAIProviderConfig
│   │   ├── LocalProviderConfig
│   │   └── E2EConfig
│   │
│   └── e2e_types.py       ◀─── New E2E types (E2EResult)
│       ├── GenerationResult
│       ├── StatusResult
│       ├── ArtifactResult
│       ├── E2EResult
│       └── E2EFailure
│
├── examples/
│   ├── e2e_config_debuggai.yaml
│   ├── e2e_config_local.yaml
│   └── e2e_usage_example.py
│
├── tests/
│   ├── test_e2e_config.py
│   └── test_e2e_types.py
│
└── E2E_CONFIG_ARCHITECTURE.md
└── E2E_CONFIG_SUMMARY.md
└── E2E_ARCHITECTURE_DIAGRAM.md  (this file)
```

## Strict Principles Visualization

```
┌────────────────────────────────────────────────────────────────┐
│                      STRICT PRINCIPLES                          │
└────────────────────────────────────────────────────────────────┘

Principle 1: No Config Discovery
─────────────────────────────────
❌ config = find_e2e_config()         # Searches cwd
✅ config = load_from_dict(yaml_dict) # Explicit dict

Principle 2: No Cascading Fallbacks
────────────────────────────────────
❌ api_key = config.get("api_key") or os.getenv("KEY") or "default"
✅ api_key = config.api_key  # Required field, no fallback

Principle 3: No Magic Values
─────────────────────────────
❌ output_dir = Path("./output")      # Relative (depends on cwd)
❌ api_url = "https://api.debugg.ai"  # Default in code
✅ output_dir = Path("/tmp/e2e")      # Absolute (explicit)
✅ api_url from config (required)     # Must be in config

Principle 4: Fail Fast
──────────────────────
❌ if api_key: ... else: log("missing key")  # Soft failure
✅ api_key: str = Field(...)                  # Hard requirement
   └─▶ ValueError at config load if missing
```

## Type Safety

```
┌────────────────────────────────────────────────────────────────┐
│                      Type Safety Guarantees                     │
└────────────────────────────────────────────────────────────────┘

Pydantic Models (Runtime Validation)
─────────────────────────────────────
class E2EConfig(BaseModel):
    provider: Literal["debuggai", "local"]  ◀─── Only these values
    output_dir: Path                        ◀─── Must be Path
    timeout_seconds: int                    ◀─── Must be int

    @field_validator("output_dir")
    def check_absolute(cls, v):
        if not v.is_absolute():
            raise ValueError(...)           ◀─── Custom validation

Result:
  ✓ Invalid values rejected at config load
  ✓ Type errors caught before runtime
  ✓ Clear error messages for debugging
```

## Error Handling

```
┌────────────────────────────────────────────────────────────────┐
│                      Error Handling Flow                        │
└────────────────────────────────────────────────────────────────┘

Config Load Error
─────────────────
try:
    config = E2EConfig.for_debuggai(
        api_key="",  # Invalid
        ...
    )
except ValueError as e:
    # Handle: "api_key cannot be empty"
    │
    ├─▶ Log error
    ├─▶ Show user-friendly message
    └─▶ Exit with code 2

Runtime Error (Generation Failed)
──────────────────────────────────
result = E2EResult.from_error(
    error_message="API authentication failed",
    provider="debuggai",
)
    │
    └─▶ verdict = ERROR
        exit_code = 2
        generation.status = "error"

Runtime Error (Timeout)
───────────────────────
result = E2EResult(
    ...,
    status=StatusResult(
        timeout_exceeded=True,
        error="Timeout after 300s",
    ),
)
    │
    └─▶ verdict = ERROR (timeout)
```

This architecture ensures that E2E configuration is:
- **Explicit**: No hidden behavior
- **Type-safe**: Pydantic validates at runtime
- **Fail-fast**: Invalid configs rejected immediately
- **Testable**: Every component has test coverage
- **Maintainable**: Clear separation of concerns
