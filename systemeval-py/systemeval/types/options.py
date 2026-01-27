"""
CLI option dataclasses.

This module contains dataclasses that group related CLI parameters to reduce
function signatures. The test() command in cli_main.py uses these to organize
its many parameters into logical categories.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple


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


__all__ = [
    "TestSelectionOptions",
    "ExecutionOptions",
    "OutputOptions",
    "EnvironmentOptions",
    "PipelineOptions",
    "BrowserOptions",
    "MultiProjectOptions",
    "TestCommandOptions",
]
