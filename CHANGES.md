# Changelog

All notable changes to systemeval will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-01-21

### Added

- **Multi-Project Support (v2.0 Config)**
  - New `subprojects` array for managing multiple test targets
  - `defaults` section for shared configuration across subprojects
  - `--project` CLI flag to run specific subprojects
  - `--tags` and `--exclude-tags` for filtering by subproject tags
  - Aggregated reporting across all subprojects

- **New Adapters**
  - `VitestAdapter` for Vitest test framework (TypeScript/JavaScript)
  - `JestAdapter` for Jest test framework (TypeScript/JavaScript)
  - Both support JSON output parsing, coverage, failfast, and parallel execution

- **Code Quality Improvements**
  - Added `__all__` exports to all `__init__.py` files for explicit public API
  - Added `working_directory` context manager for safe directory changes
  - Added `SUBPROCESS_TIMEOUT_MULTIPLIER` constant in Playwright adapter
  - Improved type annotations in `render_results()` function
  - Removed unused imports across codebase

- **CLI Enhancements**
  - `--env-mode` option (auto/docker/local) replacing deprecated --docker flag
  - Multi-project table output with Rich formatting
  - JSON output for multi-project results

### Changed

- Config schema now supports both v1.0 (single project) and v2.0 (multi-project)
- `SystemEvalConfig` has new `is_multi_project` property
- Duration naming standardized: internal uses `duration`, API uses `duration_seconds`

### Fixed

- CLI test mocks now properly set `is_multi_project` attribute
- Removed unused `Verdict` import from composite.py

## [0.2.2] - 2026-01-07

### Added

- Repository abstraction layer for PipelineAdapter
- `ProjectRepository` protocol for framework-agnostic data access
- `DjangoProjectRepository` for Django ORM integration
- `MockProjectRepository` for testing without Django

### Changed

- PipelineAdapter now uses dependency injection for repository access
- Improved testability of adapter code

## [0.2.1] - 2026-01-04

### Added

- Initial multi-adapter support
- Playwright adapter for browser testing
- Surfer adapter for web crawling tests

## [0.2.0] - 2025-12-30

### Added

- Environment abstraction layer
- Docker Compose environment support
- Composite environments for multi-service testing
- Ngrok environment for tunnel creation
- Browser environment for E2E testing

## [0.1.0] - 2025-12-15

### Added

- Initial release
- Core evaluation framework
- Pytest adapter
- CLI with test, init, validate commands
- JSON and template-based output
- Configuration via systemeval.yaml
