"""
Shared type definitions for SystemEval.

This module contains core types used across adapters, environments, and evaluation
to avoid circular dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class Verdict(str, Enum):
    """Binary verdict - deterministic, no subjective interpretation."""
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


# ============================================================================
# Adapter Configuration
# ============================================================================


@dataclass
class AdapterConfig:
    """
    Standardized configuration for test framework adapters.

    This dataclass provides a consistent interface for configuring adapters,
    replacing the varied constructor signatures across different adapter types.

    Common fields are defined at the top level, while adapter-specific settings
    are stored in the `extra` dictionary.

    Usage:
        # Basic configuration
        config = AdapterConfig(project_root="/path/to/project")

        # With test directory and markers
        config = AdapterConfig(
            project_root="/path/to/project",
            test_directory="tests",
            markers=["unit", "integration"],
        )

        # With adapter-specific settings
        config = AdapterConfig(
            project_root="/path/to/project",
            extra={
                "config_file": "playwright.config.ts",
                "headed": True,
            }
        )
    """

    # Required: path to the project root directory
    project_root: Union[str, Path]
    """Absolute path to the project root directory."""

    # Test discovery and filtering
    test_directory: Optional[str] = None
    """Relative path to test directory from project_root (e.g., 'tests')."""

    markers: List[str] = field(default_factory=list)
    """List of test markers/categories to filter by (e.g., ['unit', 'integration'])."""

    # Execution options
    parallel: bool = False
    """Enable parallel test execution."""

    coverage: bool = False
    """Enable coverage collection."""

    timeout: Optional[int] = None
    """Default timeout in seconds for test execution."""

    verbose: bool = False
    """Enable verbose output."""

    # Adapter-specific configuration
    extra: Dict[str, Any] = field(default_factory=dict)
    """
    Adapter-specific configuration options.

    Examples:
        - PytestAdapter: {}  # Uses defaults
        - PlaywrightAdapter: {"config_file": "playwright.config.ts", "headed": True}
        - SurferAdapter: {"project_slug": "my-project", "api_key": "..."}
        - PipelineAdapter: {"retry_config": RetryConfig(...)}
    """

    def __post_init__(self) -> None:
        """Validate and normalize configuration."""
        # Ensure project_root is a string
        if isinstance(self.project_root, Path):
            self.project_root = str(self.project_root)

        # Validate project_root is absolute
        if not Path(self.project_root).is_absolute():
            raise ValueError(
                f"project_root must be an absolute path, got: {self.project_root}"
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Get an extra configuration value with a default."""
        return self.extra.get(key, default)

    def with_extra(self, **kwargs: Any) -> "AdapterConfig":
        """Create a new config with additional extra settings."""
        new_extra = {**self.extra, **kwargs}
        return AdapterConfig(
            project_root=self.project_root,
            test_directory=self.test_directory,
            markers=self.markers.copy(),
            parallel=self.parallel,
            coverage=self.coverage,
            timeout=self.timeout,
            verbose=self.verbose,
            extra=new_extra,
        )

    @classmethod
    def from_project_root(cls, project_root: Union[str, Path]) -> "AdapterConfig":
        """Create a minimal config with just the project root."""
        return cls(project_root=project_root)


@dataclass
class TestItem:
    """Represents a single test item discovered by an adapter."""

    id: str
    name: str
    path: str
    markers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Location info (optional, for parity with TypeScript)
    line: Optional[int] = None
    column: Optional[int] = None
    suite: Optional[str] = None


@dataclass
class TestFailure:
    """Represents a test failure with details."""

    test_id: str
    test_name: str
    message: str
    traceback: Optional[str] = None
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Assertion details (optional, for parity with TypeScript)
    expected: Optional[Any] = None
    actual: Optional[Any] = None


@dataclass
class TestResult:
    """Test execution results with objective verdict."""

    passed: int
    failed: int
    errors: int
    skipped: int
    duration: float
    failures: List[TestFailure] = field(default_factory=list)
    total: Optional[int] = None
    exit_code: int = 0
    coverage_percent: Optional[float] = None
    category: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    parsing_warning: Optional[str] = None  # Warning when output format is unrecognized
    parsed_from: Optional[str] = None  # Source of parsed data: "pytest", "jest", "playwright", "json", "fallback"

    # Pipeline adapter metadata (used by PipelineAdapter for detailed evaluation)
    pipeline_tests: Optional[List["TestItem"]] = field(default=None, repr=False)
    pipeline_metrics: Optional[Dict[str, Any]] = field(default=None, repr=False)
    pipeline_adapter: Optional[Any] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Calculate total if not provided."""
        if self.total is None:
            self.total = self.passed + self.failed + self.errors + self.skipped

    @property
    def verdict(self) -> Verdict:
        """Determine objective verdict based on results."""
        if self.exit_code == 2:
            return Verdict.ERROR
        if self.total == 0:
            return Verdict.ERROR
        # When output format is unrecognized and command failed, report ERROR not FAIL
        # This prevents false positives from guessed test counts
        if self.parsed_from == "fallback" and self.exit_code != 0:
            return Verdict.ERROR
        if self.failed > 0 or self.errors > 0:
            return Verdict.FAIL
        return Verdict.PASS

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_seconds": round(self.duration, 3),
            "timestamp": self.timestamp,
            "category": self.category,
            "coverage_percent": self.coverage_percent,
        }
        if self.parsing_warning:
            result["parsing_warning"] = self.parsing_warning
        if self.parsed_from:
            result["parsed_from"] = self.parsed_from
        return result

    def to_evaluation(
        self,
        adapter_type: str = "unknown",
        project_name: Optional[str] = None,
    ) -> "EvaluationResult":
        """Convert TestResult to unified EvaluationResult.

        Note: Import is deferred to avoid circular dependency.
        """
        from systemeval.core.evaluation import (
            EvaluationResult,
            create_evaluation,
            create_session,
            metric,
        )

        result = create_evaluation(
            adapter_type=adapter_type,
            category=self.category,
            project_name=project_name,
        )

        # Create session from test results
        session = create_session(self.category or "tests")

        # Add core metrics
        session.metrics.append(metric(
            name="tests_passed",
            value=self.passed,
            expected=">0",
            condition=self.passed > 0 or self.total == 0,
            message=f"{self.passed} tests passed",
        ))

        session.metrics.append(metric(
            name="tests_failed",
            value=self.failed,
            expected="0",
            condition=self.failed == 0,
            message=f"{self.failed} tests failed" if self.failed else None,
        ))

        session.metrics.append(metric(
            name="tests_errors",
            value=self.errors,
            expected="0",
            condition=self.errors == 0,
            message=f"{self.errors} test errors" if self.errors else None,
        ))

        if self.coverage_percent is not None:
            session.metrics.append(metric(
                name="coverage_percent",
                value=self.coverage_percent,
                expected=">=0",
                condition=True,  # Coverage is informational
                message=f"{self.coverage_percent:.1f}% coverage",
                severity="info",
            ))

        session.duration_seconds = self.duration

        # Add failure details to session metadata
        if self.failures:
            session.metadata["failures"] = [
                {
                    "test_id": f.test_id,
                    "test_name": f.test_name,
                    "message": f.message,
                    "duration_seconds": f.duration,
                }
                for f in self.failures
            ]

        result.add_session(session)
        result.metadata.duration_seconds = self.duration
        result.finalize()

        return result


# ============================================================================
# CLI Option Dataclasses
# ============================================================================
# These dataclasses group related CLI parameters to reduce function signatures.
# The test() command in cli.py uses these to organize its 24+ parameters.


@dataclass
class TestSelectionOptions:
    """Options for selecting which tests to run."""

    category: Optional[str] = None
    """Test category to run (unit, integration, api, pipeline)."""

    app: Optional[str] = None
    """Specific app/module to test."""

    file_path: Optional[str] = None
    """Specific test file to run."""

    suite: Optional[str] = None
    """Test suite to run (e2e, integration, unit)."""


@dataclass
class ExecutionOptions:
    """Options controlling test execution behavior."""

    parallel: bool = False
    """Run tests in parallel."""

    failfast: bool = False
    """Stop on first failure."""

    verbose: bool = False
    """Verbose output."""

    coverage: bool = False
    """Collect coverage data."""


@dataclass
class OutputOptions:
    """Options controlling output format."""

    json_output: bool = False
    """Output results as JSON."""

    template: Optional[str] = None
    """Output template (summary, markdown, ci, github, junit, slack, table, pipeline_*)."""


@dataclass
class EnvironmentOptions:
    """Options controlling the test environment."""

    env_mode: str = "auto"
    """Execution environment: auto (detect), docker (force Docker), local (force local host)."""

    env_name: Optional[str] = None
    """Environment to run tests in (backend, frontend, full-stack)."""

    config: Optional[str] = None
    """Path to config file."""

    keep_running: bool = False
    """Keep containers/services running after tests."""


@dataclass
class PipelineOptions:
    """Options specific to the pipeline adapter."""

    projects: Tuple[str, ...] = field(default_factory=tuple)
    """Project slugs to evaluate (pipeline adapter)."""

    timeout: Optional[int] = None
    """Max wait time per project in seconds (pipeline adapter)."""

    poll_interval: Optional[int] = None
    """Seconds between status checks (pipeline adapter)."""

    sync: bool = False
    """Run webhooks synchronously (pipeline adapter)."""

    skip_build: bool = False
    """Skip build, use existing containers (pipeline adapter)."""


@dataclass
class BrowserOptions:
    """Options specific to browser testing."""

    browser: bool = False
    """Run Playwright browser tests."""

    surfer: bool = False
    """Run DebuggAI Surfer cloud E2E tests."""

    tunnel_port: Optional[int] = None
    """Port to expose via ngrok tunnel for browser tests."""

    headed: bool = False
    """Run browser tests in headed mode (Playwright only)."""


@dataclass
class MultiProjectOptions:
    """Options for multi-project execution (v2.0 config)."""

    subprojects: Tuple[str, ...] = field(default_factory=tuple)
    """Specific subprojects to run (by name). Empty = run all enabled."""

    tags: Tuple[str, ...] = field(default_factory=tuple)
    """Only run subprojects with these tags."""

    exclude_tags: Tuple[str, ...] = field(default_factory=tuple)
    """Exclude subprojects with these tags."""


@dataclass
class TestCommandOptions:
    """
    Aggregated options for the test command.

    This dataclass groups all CLI options into logical categories to reduce
    the number of parameters in the test() function signature.
    """

    selection: TestSelectionOptions = field(default_factory=TestSelectionOptions)
    """Test selection options (category, app, file, suite)."""

    execution: ExecutionOptions = field(default_factory=ExecutionOptions)
    """Execution options (parallel, failfast, verbose, coverage)."""

    output: OutputOptions = field(default_factory=OutputOptions)
    """Output options (json, template)."""

    environment: EnvironmentOptions = field(default_factory=EnvironmentOptions)
    """Environment options (env_mode, env_name, config, keep_running)."""

    pipeline: PipelineOptions = field(default_factory=PipelineOptions)
    """Pipeline adapter options (projects, timeout, poll_interval, sync, skip_build)."""

    browser_opts: BrowserOptions = field(default_factory=BrowserOptions)
    """Browser testing options (browser, surfer, tunnel_port, headed)."""

    multi_project: MultiProjectOptions = field(default_factory=MultiProjectOptions)
    """Multi-project options (subprojects, tags, exclude_tags)."""

    @classmethod
    def from_cli_args(
        cls,
        # Test selection
        category: Optional[str] = None,
        app: Optional[str] = None,
        file_path: Optional[str] = None,
        suite: Optional[str] = None,
        # Execution
        parallel: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        coverage: bool = False,
        # Output
        json_output: bool = False,
        template: Optional[str] = None,
        # Environment
        env_mode: str = "auto",
        env_name: Optional[str] = None,
        config: Optional[str] = None,
        keep_running: bool = False,
        # Pipeline
        projects: Tuple[str, ...] = (),
        timeout: Optional[int] = None,
        poll_interval: Optional[int] = None,
        sync: bool = False,
        skip_build: bool = False,
        # Browser
        browser: bool = False,
        surfer: bool = False,
        tunnel_port: Optional[int] = None,
        headed: bool = False,
        # Multi-project
        subprojects: Tuple[str, ...] = (),
        tags: Tuple[str, ...] = (),
        exclude_tags: Tuple[str, ...] = (),
    ) -> "TestCommandOptions":
        """
        Create TestCommandOptions from individual CLI arguments.

        This factory method preserves backward compatibility with Click's
        parameter injection while organizing options into logical groups.
        """
        return cls(
            selection=TestSelectionOptions(
                category=category,
                app=app,
                file_path=file_path,
                suite=suite,
            ),
            execution=ExecutionOptions(
                parallel=parallel,
                failfast=failfast,
                verbose=verbose,
                coverage=coverage,
            ),
            output=OutputOptions(
                json_output=json_output,
                template=template,
            ),
            environment=EnvironmentOptions(
                env_mode=env_mode,
                env_name=env_name,
                config=config,
                keep_running=keep_running,
            ),
            pipeline=PipelineOptions(
                projects=projects,
                timeout=timeout,
                poll_interval=poll_interval,
                sync=sync,
                skip_build=skip_build,
            ),
            browser_opts=BrowserOptions(
                browser=browser,
                surfer=surfer,
                tunnel_port=tunnel_port,
                headed=headed,
            ),
            multi_project=MultiProjectOptions(
                subprojects=subprojects,
                tags=tags,
                exclude_tags=exclude_tags,
            ),
        )
