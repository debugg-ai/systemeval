"""
TestRunner service - Core test execution business logic.

This module extracts test execution logic from the CLI, providing:
- A unified API for running tests across all modes
- Framework-agnostic test execution
- Programmatic access (not just CLI)
- Testable components

Usage:
    from systemeval.services import TestRunner, TestRunnerConfig

    config = TestRunnerConfig.from_yaml("systemeval.yaml")
    runner = TestRunner(config)

    # Run tests with adapter
    result = runner.run_adapter_tests(category="unit")

    # Run in environment
    result = runner.run_with_environment(env_name="backend")

    # Run browser tests
    result = runner.run_browser_tests(runner="playwright")
"""

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

from systemeval.adapters import get_adapter
from systemeval.config import (
    SystemEvalConfig,
    SubprojectConfig,
    SubprojectResult,
    MultiProjectResult,
    get_subproject_absolute_path,
    load_config,
)
from systemeval.types import (
    AdapterConfig,
    TestResult,
    TestCommandOptions,
)


class ProgressCallback(Protocol):
    """Protocol for progress reporting during test execution."""

    def on_start(self, message: str) -> None:
        """Called when a phase starts."""
        ...

    def on_progress(self, message: str) -> None:
        """Called for progress updates."""
        ...

    def on_complete(self, message: str, success: bool) -> None:
        """Called when a phase completes."""
        ...


@dataclass
class NullProgressCallback:
    """No-op progress callback for silent execution."""

    def on_start(self, message: str) -> None:
        pass

    def on_progress(self, message: str) -> None:
        pass

    def on_complete(self, message: str, success: bool) -> None:
        pass


@dataclass
class TestRunnerConfig:
    """Configuration for TestRunner.

    Separates runner configuration from SystemEvalConfig to allow
    programmatic configuration without YAML files.
    """

    # Core settings
    project_root: Path
    adapter: str = "pytest"
    test_directory: str = "tests"

    # Execution options
    parallel: bool = False
    coverage: bool = False
    failfast: bool = False
    verbose: bool = False
    timeout: Optional[int] = None

    # Environment options
    env_name: Optional[str] = None
    keep_running: bool = False
    skip_build: bool = False

    # Browser options
    browser_runner: Optional[str] = None  # "playwright" or "surfer"
    tunnel_port: Optional[int] = None
    headed: bool = False

    # Multi-project options
    subproject_names: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    exclude_tags: Optional[List[str]] = None

    # Full config (optional, for advanced features)
    _system_config: Optional[SystemEvalConfig] = field(default=None, repr=False)

    @classmethod
    def from_yaml(cls, config_path: Union[str, Path]) -> "TestRunnerConfig":
        """Load configuration from YAML file."""
        path = Path(config_path)
        system_config = load_config(path)

        return cls(
            project_root=system_config.project_root,
            adapter=system_config.adapter,
            test_directory=str(system_config.test_directory),
            _system_config=system_config,
        )

    @classmethod
    def from_system_config(cls, config: SystemEvalConfig) -> "TestRunnerConfig":
        """Create from existing SystemEvalConfig."""
        return cls(
            project_root=config.project_root,
            adapter=config.adapter,
            test_directory=str(config.test_directory),
            _system_config=config,
        )

    @property
    def system_config(self) -> Optional[SystemEvalConfig]:
        """Access underlying SystemEvalConfig if available."""
        return self._system_config


@dataclass
class RunResult:
    """Result of a test run, wrapping TestResult with additional context."""

    test_result: TestResult
    mode: str  # "adapter", "browser", "environment", "multi-project"
    duration: float = 0.0
    environment: Optional[str] = None
    subprojects: Optional[List[SubprojectResult]] = None

    @property
    def success(self) -> bool:
        """Whether the run was successful (PASS verdict)."""
        return self.test_result.verdict.value == "PASS"

    @property
    def exit_code(self) -> int:
        """Exit code for CLI or subprocess use."""
        return self.test_result.exit_code


class TestRunner:
    """Core test execution service.

    Provides programmatic API for running tests across all modes:
    - Adapter-based (pytest, jest, etc.)
    - Browser (Playwright, Surfer)
    - Environment orchestration (Docker Compose, etc.)
    - Multi-project (v2.0 subprojects)
    """

    def __init__(
        self,
        config: TestRunnerConfig,
        progress: Optional[ProgressCallback] = None,
    ):
        """Initialize TestRunner.

        Args:
            config: Runner configuration.
            progress: Optional callback for progress reporting.
        """
        self.config = config
        self.progress = progress or NullProgressCallback()

    def run(
        self,
        *,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file_path: Optional[str] = None,
        suite: Optional[str] = None,
    ) -> RunResult:
        """Run tests using the most appropriate mode.

        Automatically selects mode based on configuration:
        - Multi-project mode if subprojects configured
        - Browser mode if browser_runner set
        - Environment mode if environments configured
        - Adapter mode otherwise

        Args:
            category: Test category filter.
            app: App/module filter.
            file_path: Specific file filter.
            suite: Test suite name (for environments).

        Returns:
            RunResult with test results and metadata.
        """
        sys_config = self.config.system_config

        # Check mode priority
        if sys_config and sys_config.is_multi_project:
            return self.run_multi_project()

        if self.config.browser_runner:
            return self.run_browser_tests()

        if self.config.env_name or (sys_config and sys_config.environments):
            return self.run_with_environment(suite=suite, category=category)

        return self.run_adapter_tests(
            category=category, app=app, file_path=file_path
        )

    def run_adapter_tests(
        self,
        *,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> RunResult:
        """Run tests using configured adapter.

        Args:
            category: Test category to filter.
            app: App/module to filter.
            file_path: Specific test file.

        Returns:
            RunResult with adapter execution results.
        """
        self.progress.on_start(f"Running tests with {self.config.adapter} adapter")

        start_time = time.time()

        try:
            adapter = get_adapter(
                self.config.adapter,
                str(self.config.project_root.absolute()),
            )
        except (KeyError, ValueError) as e:
            return RunResult(
                test_result=TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=0.0,
                    exit_code=2,
                    error_message=str(e),
                ),
                mode="adapter",
                duration=time.time() - start_time,
            )

        # Validate environment
        if not adapter.validate_environment():
            self.progress.on_progress("Environment validation warning")

        # Execute tests
        result = adapter.execute(
            tests=None,
            parallel=self.config.parallel,
            coverage=self.config.coverage,
            failfast=self.config.failfast,
            verbose=self.config.verbose,
        )

        duration = time.time() - start_time
        self.progress.on_complete(
            f"Completed: {result.passed} passed, {result.failed} failed",
            result.verdict.value == "PASS",
        )

        return RunResult(
            test_result=result,
            mode="adapter",
            duration=duration,
        )

    def run_browser_tests(
        self,
        *,
        category: Optional[str] = None,
    ) -> RunResult:
        """Run browser tests using Playwright or Surfer.

        Args:
            category: Test category filter.

        Returns:
            RunResult with browser test results.
        """
        from systemeval.environments import BrowserEnvironment

        runner = self.config.browser_runner or "playwright"
        self.progress.on_start(f"Running {runner} browser tests")

        start_time = time.time()

        # Build browser environment config
        browser_config: Dict[str, Any] = {
            "test_runner": runner,
            "working_dir": str(self.config.project_root.absolute()),
        }

        # Add tunnel config
        if self.config.tunnel_port:
            browser_config["tunnel"] = {"port": self.config.tunnel_port}

        # Add adapter-specific config from system config
        sys_config = self.config.system_config
        if sys_config:
            if runner == "playwright" and sys_config.playwright_config:
                pw_conf = sys_config.playwright_config
                browser_config["playwright"] = {
                    "config_file": pw_conf.config_file,
                    "project": pw_conf.project,
                    "headed": self.config.headed or pw_conf.headed,
                    "timeout": pw_conf.timeout,
                }
            elif runner == "surfer" and sys_config.surfer_config:
                sf_conf = sys_config.surfer_config
                browser_config["surfer"] = {
                    "project_slug": sf_conf.project_slug,
                    "api_key": sf_conf.api_key,
                    "api_base_url": sf_conf.api_base_url,
                    "poll_interval": sf_conf.poll_interval,
                    "timeout": self.config.timeout or sf_conf.timeout,
                }

        # Headed mode without full config
        if runner == "playwright" and self.config.headed:
            browser_config.setdefault("playwright", {})["headed"] = True

        # Create environment
        env = BrowserEnvironment("browser-tests", browser_config)

        try:
            # Setup tunnel if configured
            if self.config.tunnel_port:
                self.progress.on_progress("Starting tunnel...")
                setup_result = env.setup()
                if not setup_result.success:
                    return RunResult(
                        test_result=TestResult(
                            passed=0,
                            failed=0,
                            errors=1,
                            skipped=0,
                            duration=setup_result.duration,
                            exit_code=2,
                            error_message=setup_result.message,
                        ),
                        mode="browser",
                        duration=time.time() - start_time,
                    )

                if not env.wait_ready(timeout=60):
                    env.teardown()
                    return RunResult(
                        test_result=TestResult(
                            passed=0,
                            failed=0,
                            errors=1,
                            skipped=0,
                            duration=env.timings.startup,
                            exit_code=2,
                            error_message="Tunnel did not become ready",
                        ),
                        mode="browser",
                        duration=time.time() - start_time,
                    )

                self.progress.on_progress(f"Tunnel ready: {env.tunnel_url}")

            # Run tests
            self.progress.on_progress("Running browser tests...")
            result = env.run_tests(category=category, verbose=self.config.verbose)

            duration = time.time() - start_time
            self.progress.on_complete(
                f"Completed: {result.passed} passed, {result.failed} failed",
                result.verdict.value == "PASS",
            )

            return RunResult(
                test_result=result,
                mode="browser",
                duration=duration,
            )

        finally:
            if not self.config.keep_running:
                env.teardown()

    def run_with_environment(
        self,
        *,
        suite: Optional[str] = None,
        category: Optional[str] = None,
    ) -> RunResult:
        """Run tests in configured environment.

        Args:
            suite: Test suite to run.
            category: Test category filter.

        Returns:
            RunResult with environment execution results.
        """
        from systemeval.environments import EnvironmentResolver

        sys_config = self.config.system_config
        if not sys_config or not sys_config.environments:
            return RunResult(
                test_result=TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=0.0,
                    exit_code=2,
                    error_message="No environments configured",
                ),
                mode="environment",
                duration=0.0,
            )

        # Resolve environment
        resolver = EnvironmentResolver(sys_config.environments)
        env_name = self.config.env_name or resolver.get_default_environment()

        if not env_name:
            return RunResult(
                test_result=TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=0.0,
                    exit_code=2,
                    error_message="No default environment found",
                ),
                mode="environment",
                duration=0.0,
            )

        self.progress.on_start(f"Running tests in '{env_name}' environment")
        start_time = time.time()

        try:
            env = resolver.resolve(env_name)
        except (KeyError, ValueError) as e:
            return RunResult(
                test_result=TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=0.0,
                    exit_code=2,
                    error_message=str(e),
                ),
                mode="environment",
                duration=time.time() - start_time,
            )

        # Inject skip_build if applicable
        if self.config.skip_build and hasattr(env, "skip_build"):
            env.skip_build = self.config.skip_build

        try:
            # Setup
            self.progress.on_progress("Setting up environment...")
            setup_result = env.setup()
            if not setup_result.success:
                return RunResult(
                    test_result=TestResult(
                        passed=0,
                        failed=0,
                        errors=1,
                        skipped=0,
                        duration=setup_result.duration,
                        exit_code=2,
                        error_message=setup_result.message,
                    ),
                    mode="environment",
                    duration=time.time() - start_time,
                    environment=env_name,
                )

            self.progress.on_progress(
                f"Environment started ({setup_result.duration:.1f}s)"
            )

            # Wait for ready
            self.progress.on_progress("Waiting for services...")
            if not env.wait_ready():
                env.teardown()
                return RunResult(
                    test_result=TestResult(
                        passed=0,
                        failed=0,
                        errors=1,
                        skipped=0,
                        duration=env.timings.startup + env.timings.health_check,
                        exit_code=2,
                        error_message="Environment did not become ready",
                    ),
                    mode="environment",
                    duration=time.time() - start_time,
                    environment=env_name,
                )

            self.progress.on_progress(
                f"Services ready ({env.timings.health_check:.1f}s)"
            )

            # Run tests
            self.progress.on_progress("Running tests...")
            result = env.run_tests(
                suite=suite, category=category, verbose=self.config.verbose
            )

            duration = time.time() - start_time
            self.progress.on_complete(
                f"Completed: {result.passed} passed, {result.failed} failed",
                result.verdict.value == "PASS",
            )

            return RunResult(
                test_result=result,
                mode="environment",
                duration=duration,
                environment=env_name,
            )

        finally:
            if not self.config.keep_running:
                self.progress.on_progress("Tearing down environment...")
                env.teardown(keep_running=self.config.keep_running)

    def run_multi_project(self) -> RunResult:
        """Run tests across multiple subprojects.

        Returns:
            RunResult with aggregated multi-project results.
        """
        sys_config = self.config.system_config
        if not sys_config:
            return RunResult(
                test_result=TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=0.0,
                    exit_code=2,
                    error_message="No system config for multi-project",
                ),
                mode="multi-project",
                duration=0.0,
            )

        start_time = time.time()

        # Get filtered subprojects
        subprojects = sys_config.get_enabled_subprojects(
            tags=self.config.tags, names=self.config.subproject_names
        )

        # Exclude tags
        if self.config.exclude_tags:
            subprojects = [
                sp
                for sp in subprojects
                if not any(tag in sp.tags for tag in self.config.exclude_tags)
            ]

        if not subprojects:
            return RunResult(
                test_result=TestResult(
                    passed=0,
                    failed=0,
                    errors=0,
                    skipped=0,
                    duration=0.0,
                    exit_code=0,
                ),
                mode="multi-project",
                duration=0.0,
            )

        self.progress.on_start(f"Running {len(subprojects)} subproject(s)")

        multi_result = MultiProjectResult()

        for sp in subprojects:
            sp_result = self._run_single_subproject(sys_config, sp)
            multi_result.subprojects.append(sp_result)

        multi_result.calculate_totals()

        duration = time.time() - start_time
        self.progress.on_complete(
            f"Completed: {multi_result.total_passed} passed, {multi_result.total_failed} failed",
            multi_result.verdict == "PASS",
        )

        # Convert to TestResult for unified interface
        test_result = TestResult(
            passed=multi_result.total_passed,
            failed=multi_result.total_failed,
            errors=multi_result.total_errors,
            skipped=multi_result.total_skipped,
            duration=duration,
            exit_code=0 if multi_result.verdict == "PASS" else 1,
        )

        return RunResult(
            test_result=test_result,
            mode="multi-project",
            duration=duration,
            subprojects=multi_result.subprojects,
        )

    def _run_single_subproject(
        self,
        root_config: SystemEvalConfig,
        subproject: SubprojectConfig,
    ) -> SubprojectResult:
        """Run tests for a single subproject.

        Args:
            root_config: Root system configuration.
            subproject: Subproject to run.

        Returns:
            SubprojectResult with test results.
        """
        self.progress.on_progress(f"Running {subproject.name} ({subproject.adapter})")

        sp_path = get_subproject_absolute_path(root_config, subproject)

        # Check path exists
        if not sp_path.exists():
            return SubprojectResult(
                name=subproject.name,
                adapter=subproject.adapter,
                status="ERROR",
                error_message=f"Subproject path not found: {sp_path}",
            )

        # Run pre_commands
        if subproject.pre_commands:
            for cmd in subproject.pre_commands:
                try:
                    subprocess.run(
                        cmd,
                        shell=True,
                        cwd=str(sp_path),
                        check=True,
                        capture_output=not self.config.verbose,
                        env={**os.environ, **subproject.env},
                    )
                except subprocess.CalledProcessError:
                    return SubprojectResult(
                        name=subproject.name,
                        adapter=subproject.adapter,
                        status="ERROR",
                        error_message=f"Pre-command failed: {cmd}",
                    )

        # Get adapter
        try:
            adapter_name = subproject.adapter
            if adapter_name == "pytest-django":
                adapter_name = "pytest"

            adapter = get_adapter(adapter_name, str(sp_path))

        except (KeyError, ValueError) as e:
            return SubprojectResult(
                name=subproject.name,
                adapter=subproject.adapter,
                status="ERROR",
                error_message=f"Adapter error: {e}",
            )

        # Set environment variables
        env_backup = {}
        for key, value in subproject.env.items():
            env_backup[key] = os.environ.get(key)
            os.environ[key] = value

        try:
            start_time = time.time()
            test_result = adapter.execute(
                tests=None,
                parallel=self.config.parallel,
                coverage=self.config.coverage,
                failfast=self.config.failfast,
                verbose=self.config.verbose,
            )
            duration = time.time() - start_time

            return SubprojectResult(
                name=subproject.name,
                adapter=subproject.adapter,
                passed=test_result.passed,
                failed=test_result.failed,
                errors=test_result.errors,
                skipped=test_result.skipped,
                duration=duration,
                status=(
                    "PASS"
                    if test_result.verdict.value == "PASS"
                    else ("ERROR" if test_result.verdict.value == "ERROR" else "FAIL")
                ),
                failures=[
                    {
                        "test": f.test_id,
                        "name": f.test_name,
                        "message": f.message,
                    }
                    for f in test_result.failures
                ],
            )

        except Exception as e:
            return SubprojectResult(
                name=subproject.name,
                adapter=subproject.adapter,
                status="ERROR",
                error_message=str(e),
            )

        finally:
            # Restore environment
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
