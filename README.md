# SystemEval

Unified test runner CLI with framework-agnostic adapters. One command to run tests in any project.

## Installation

```bash
# Install from PyPI
pip install systemeval

# Install with pytest support (recommended)
pip install systemeval[pytest]

# Install from source
pip install -e ".[pytest]"
```

## Quick Start

```bash
# Initialize config in your project
systemeval init

# Run tests
systemeval test                          # Run default category
systemeval test --category unit          # Run unit tests
systemeval test --category integration   # Run integration tests
systemeval test --app agents             # Run tests for specific app
systemeval test --file path/to/test.py   # Run specific file

# Options
systemeval test --parallel               # Parallel execution
systemeval test --coverage               # With coverage report
systemeval test --json                   # JSON output for CI
systemeval test --verbose                # Detailed output
```

## Configuration

Create `systemeval.yaml` in your project root:

```yaml
project:
  name: my-project
  type: django

# Which adapter to use
adapter: pytest

# Adapter-specific config
pytest:
  config_file: pytest.ini
  base_path: backend/
  default_category: unit

# Test categories
categories:
  unit:
    markers: [unit]
    description: "Unit tests - isolated, no external dependencies"
  integration:
    markers: [integration]
    description: "Integration tests - multiple components together"
  api:
    markers: [api]
    description: "API endpoint tests"
  pipeline:
    markers: [pipeline]
    description: "Full pipeline tests"
    requires: [docker]

# Environment detection
environment:
  docker:
    detection:
      - file: /.dockerenv
      - env: DOCKER_CONTAINER=true
  local:
    database: sqlite

# Output settings
reporting:
  format: table
  colors: true
```

## Commands

| Command | Description |
|---------|-------------|
| `systemeval test` | Run tests |
| `systemeval init` | Create config file |
| `systemeval validate` | Validate config |
| `systemeval list categories` | Show available categories |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | One or more tests failed |
| 2 | Configuration or execution error |

## Adapters

### Pytest (Default)

Works with any Python project using pytest:

```yaml
adapter: pytest
pytest:
  config_file: pytest.ini
  base_path: .
  default_category: unit
```

### Jest (Coming Soon)

For JavaScript/TypeScript projects:

```yaml
adapter: jest
jest:
  config_file: jest.config.js
```

## Key Design Principles

1. **One Command**: `systemeval test` works the same in every project
2. **Adapter Pattern**: Test framework is an implementation detail
3. **Deterministic**: Exit codes 0/1/2 only - no ambiguity
4. **Docker-Aware**: Auto-detects container environment
5. **CI-Friendly**: JSON output, proper exit codes

## License

MIT License - see [LICENSE](LICENSE) for details.
