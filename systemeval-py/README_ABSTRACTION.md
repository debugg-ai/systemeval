# Pipeline Adapter Django Decoupling - Quick Reference

## Problem Solved

**Issue SE-dhh**: Pipeline Adapter had direct Django ORM imports violating adapter pattern principles.

## Solution

Created a **repository abstraction layer** using the Repository Pattern and Dependency Inversion Principle.

## Quick Start

### Using with Django (Default)

```python
from systemeval.adapters.pipeline_adapter import PipelineAdapter

# Works exactly as before - no changes needed
adapter = PipelineAdapter('/path/to/sentinal/backend')
tests = adapter.discover()
result = adapter.execute(tests)
```

### Using for Testing (No Django)

```python
from systemeval.adapters import PipelineAdapter, MockProjectRepository

# Create mock repository
repo = MockProjectRepository()
repo.add_project({
    'id': '1',
    'name': 'Test Project',
    'slug': 'test-project',
    'repo_url': 'https://github.com/test/repo'
})

# Use adapter with mock - no Django required!
adapter = PipelineAdapter('/fake/path', repository=repo)
tests = adapter.discover()
print(f"Found {len(tests)} projects")  # Works without Django!
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    PipelineAdapter                          │
│                  (High-level Module)                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ depends on
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              ProjectRepository (Protocol)                   │
│                 (Abstraction Layer)                         │
└───────┬─────────────────────────┬──────────────────┬────────┘
        │                         │                  │
        │ implements              │ implements       │ implements
        ▼                         ▼                  ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ DjangoProject    │  │ MockProject      │  │ Custom           │
│ Repository       │  │ Repository       │  │ Repository       │
│ (Production)     │  │ (Testing)        │  │ (Your impl)      │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                      │
         ▼                     ▼                      ▼
    Django ORM            In-Memory Dict         Custom Source
```

## Key Files

| File | Purpose |
|------|---------|
| `systemeval/adapters/repositories.py` | Repository abstractions and implementations |
| `systemeval/adapters/pipeline_adapter.py` | Pipeline adapter using repository pattern |
| `examples/test_pipeline_abstraction.py` | Working example demonstrating abstraction |
| `docs/pipeline_adapter_abstraction.md` | Comprehensive documentation |

## What Changed

### Public Interface (Uses Abstraction)

- `__init__(project_root, repository=None)` - Accepts optional repository
- `validate_environment()` - Tests repository instead of Django apps
- `discover()` - Uses `repository.get_all_projects()` instead of ORM
- `execute()` - Uses `repository.get_project_by_id()` instead of ORM
- `_find_project()` - Uses `repository.find_project()` instead of ORM
- `_trigger_webhook()` - Uses repository for installations/executions

### Private Helpers (Still Use Django)

- `_poll_for_completion()` - Complex ORM queries for metrics
- `_collect_metrics()` - Complex ORM queries for diagnostics

**Why?** Abstracting these would duplicate Django ORM functionality. The abstraction is at the public interface where it matters most.

## Repository API

```python
class ProjectRepository(Protocol):
    def get_all_projects(self) -> List[Dict[str, Any]]: ...
    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]: ...
    def find_project(self, slug: str) -> Optional[Dict[str, Any]]: ...
    def get_repository(self, repo_id: int) -> Optional[Dict[str, Any]]: ...
    def get_repository_installation(self, repo_id: int) -> Optional[Dict[str, Any]]: ...
    def get_latest_pipeline_execution(self, project_id: str) -> Optional[Dict[str, Any]]: ...
```

## Testing

Run the example:
```bash
python3 examples/test_pipeline_abstraction.py
```

Expected output:
```
Testing PipelineAdapter with MockProjectRepository...
============================================================

1. Validating environment...
   Environment valid: True

2. Discovering projects...
   Found 2 projects:
   - Test Project 1 (id=1, slug=test-project-1)
     Markers: pipeline, build, health, crawl, e2e
     Repo URL: https://github.com/test/repo1
   ...

Test completed successfully!
```

## Benefits

1. **No Django Required for Testing**: Use `MockProjectRepository`
2. **Backward Compatible**: Existing code works unchanged
3. **Flexible**: Support any data source via custom repository
4. **SOLID Principles**: Proper dependency inversion
5. **Better Testability**: Easy to mock and test

## Implementation Details

### DjangoProjectRepository

- Imports Django models only in `__init__`
- Converts models to dictionaries
- Preserves `_instance` for internal use
- Fails gracefully if Django unavailable

### MockProjectRepository

- In-memory dictionary storage
- Methods: `add_project()`, `add_repository()`, `add_installation()`
- No Django dependencies
- Perfect for unit tests

## Custom Implementation Example

```python
class RedisProjectRepository:
    """Example: Projects stored in Redis"""
    def __init__(self, redis_client):
        self.redis = redis_client

    def get_all_projects(self) -> List[Dict[str, Any]]:
        keys = self.redis.keys('project:*')
        return [json.loads(self.redis.get(k)) for k in keys]

    # ... implement other methods

# Use it
repo = RedisProjectRepository(redis_client)
adapter = PipelineAdapter('/path', repository=repo)
```

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Protocol vs ABC | Duck typing, more flexible |
| Dict return types | Framework-agnostic, serializable |
| Public interface only | Private helpers too Django-specific |
| Auto-create Django repo | Backward compatibility |

## Migration Checklist

- [ ] No changes needed for existing code (backward compatible)
- [ ] For testing: Use `MockProjectRepository` with dependency injection
- [ ] For custom sources: Implement `ProjectRepository` protocol
- [ ] Review documentation: `docs/pipeline_adapter_abstraction.md`

## Related Issues

- **SE-dhh**: Pipeline Adapter Django Coupling (FIXED)

## See Also

- Full documentation: `/systemeval/docs/pipeline_adapter_abstraction.md`
- Change summary: `/systemeval/CHANGES.md`
- Working example: `/systemeval/examples/test_pipeline_abstraction.py`
- Implementation: `/systemeval/systemeval/adapters/repositories.py`
