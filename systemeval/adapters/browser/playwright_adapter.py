"""
Playwright adapter for local browser testing.

Runs Playwright tests via npx and parses JSON output for results.
"""
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from systemeval.adapters.base import AdapterConfig, BaseAdapter, TestItem, TestResult, TestFailure

logger = logging.getLogger(__name__)

# Multiplier for subprocess timeout relative to Playwright's internal timeout.
# This gives Playwright time to handle its own timeouts gracefully before
# the subprocess is forcefully killed.
SUBPROCESS_TIMEOUT_MULTIPLIER = 10


class PlaywrightAdapter(BaseAdapter):
    """
    Adapter for running local Playwright tests.

    Uses npx playwright test to execute tests and parses JSON reporter output.

    Supports initialization with either AdapterConfig or legacy parameters.

    Example:
        # Using AdapterConfig (preferred)
        config = AdapterConfig(
            project_root="/path/to/project",
            timeout=60000,
            extra={
                "config_file": "playwright.config.ts",
                "project": "chromium",
                "headed": True,
            }
        )
        adapter = PlaywrightAdapter(config)

        # Using legacy parameters (backward compatible)
        adapter = PlaywrightAdapter(
            project_root="/path/to/project",
            config_file="playwright.config.ts",
            headed=True,
        )
    """

    def __init__(
        self,
        config_or_project_root: Union[AdapterConfig, str, Path],
        config_file: str = "playwright.config.ts",
        project: Optional[str] = None,
        headed: bool = False,
        timeout: int = 30000,
    ) -> None:
        """Initialize Playwright adapter.

        Args:
            config_or_project_root: Either an AdapterConfig object or project root path.
            config_file: Path to playwright config (used only if project_root is passed).
            project: Browser project (chromium, firefox, webkit).
            headed: Run in headed mode.
            timeout: Default timeout in milliseconds.
        """
        super().__init__(config_or_project_root)

        # Extract Playwright-specific settings from config or use legacy params
        if isinstance(config_or_project_root, AdapterConfig):
            self.config_file = self.config.get("config_file", "playwright.config.ts")
            self.playwright_project = self.config.get("project", None)
            self.headed = self.config.get("headed", False)
            # Convert timeout: config uses seconds, Playwright uses milliseconds
            config_timeout = self.config.timeout
            if config_timeout:
                self.timeout = config_timeout * 1000  # seconds to ms
            else:
                self.timeout = self.config.get("timeout", 30000)
        else:
            # Legacy initialization
            self.config_file = config_file
            self.playwright_project = project
            self.headed = headed
            self.timeout = timeout

        self._npx_path: Optional[str] = None

    def _get_npx_path(self) -> str:
        """Get path to npx executable."""
        if self._npx_path is None:
            self._npx_path = shutil.which("npx")
            if not self._npx_path:
                raise RuntimeError("npx not found in PATH. Install Node.js from https://nodejs.org/")
        return self._npx_path

    def _build_base_command(self) -> List[str]:
        """Build base playwright command."""
        cmd = [self._get_npx_path(), "playwright", "test"]

        config_path = Path(self.project_root) / self.config_file
        if config_path.exists():
            cmd.extend(["--config", str(config_path)])

        if self.playwright_project:
            cmd.extend(["--project", self.playwright_project])

        if self.headed:
            cmd.append("--headed")

        return cmd

    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover Playwright tests using --list flag."""
        cmd = self._build_base_command()
        cmd.extend(["--list", "--reporter=json"])

        if file:
            cmd.append(file)

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Parse JSON output
            tests = []
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    for suite in data.get("suites", []):
                        tests.extend(self._extract_tests_from_suite(suite))
                except json.JSONDecodeError:
                    # Try line-by-line parsing for --list output
                    for line in result.stdout.strip().split("\n"):
                        if line.strip() and not line.startswith("["):
                            tests.append(TestItem(
                                id=line.strip(),
                                name=line.strip(),
                                path="",
                                markers=["browser", "e2e"],
                            ))

            return tests

        except subprocess.TimeoutExpired:
            logger.error("Test discovery timed out")
            return []
        except FileNotFoundError:
            logger.error("npx or playwright not found")
            return []

    def _extract_tests_from_suite(
        self,
        suite: Dict[str, Any],
        parent_path: str = "",
    ) -> List[TestItem]:
        """Recursively extract tests from Playwright suite JSON."""
        tests = []
        suite_title = suite.get("title", "")
        current_path = f"{parent_path} > {suite_title}" if parent_path else suite_title

        # Extract specs (test cases)
        for spec in suite.get("specs", []):
            test_id = spec.get("id", spec.get("title", ""))
            tests.append(TestItem(
                id=test_id,
                name=spec.get("title", ""),
                path=spec.get("file", ""),
                markers=["browser", "e2e"],
                metadata={
                    "line": spec.get("line"),
                    "column": spec.get("column"),
                    "suite": current_path,
                },
            ))

        # Recurse into child suites
        for child_suite in suite.get("suites", []):
            tests.extend(self._extract_tests_from_suite(child_suite, current_path))

        return tests

    def execute(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
    ) -> TestResult:
        """Execute Playwright browser tests and return structured results.

        Runs Playwright tests via npx with JSON reporter and parses the
        output into a unified TestResult format.

        Args:
            tests: Optional list of specific test files to run.
                   If None, runs all tests discovered by Playwright.
            parallel: Enable parallel workers via --workers=auto flag.
                      Set to False for --workers=1 (serial execution).
            coverage: Not applicable for Playwright E2E tests.
            failfast: Stop on first failure via --max-failures=1.
            verbose: Not directly used (Playwright output is JSON).
            timeout: Maximum execution time in seconds. Subprocess timeout
                     is multiplied by SUBPROCESS_TIMEOUT_MULTIPLIER to allow
                     Playwright's internal timeouts to complete first.

        Returns:
            TestResult with parsed Playwright results including:
            - Test counts from stats.expected/unexpected/skipped
            - Failure details extracted from suite results
            - Duration and exit code

        Note:
            Playwright timeouts are in milliseconds internally. The adapter
            converts seconds to milliseconds as needed. Uses JSON reporter
            for structured output parsing.
        """
        start_time = time.time()
        cmd = self._build_base_command()

        # Use JSON reporter for structured output
        cmd.extend(["--reporter=json"])

        if failfast:
            cmd.append("--max-failures=1")

        if parallel:
            cmd.extend(["--workers", "auto"])
        else:
            cmd.extend(["--workers", "1"])

        # Add specific test files if provided
        if tests:
            for test in tests:
                if test.path:
                    cmd.append(test.path)

        # Set timeout: convert Playwright's ms timeout to seconds with buffer multiplier
        exec_timeout = timeout or self.timeout // 1000 * SUBPROCESS_TIMEOUT_MULTIPLIER

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=exec_timeout,
                env={**os.environ, "PLAYWRIGHT_JSON_OUTPUT_NAME": "stdout"},
            )

            duration = time.time() - start_time
            return self._parse_results(result.stdout, result.stderr, result.returncode, duration)

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=duration,
                exit_code=2,
                failures=[TestFailure(
                    test_id="timeout",
                    test_name="Test Execution",
                    message=f"Test execution timed out after {exec_timeout}s",
                )],
            )
        except FileNotFoundError:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                exit_code=2,
                failures=[TestFailure(
                    test_id="setup",
                    test_name="Environment",
                    message="npx or playwright not found in PATH",
                )],
            )

    def get_command(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
    ) -> List[str]:
        """Get the Playwright command that would be used to run tests.

        Args:
            tests: Specific test items to run (None = run all)
            parallel: Enable parallel test execution
            coverage: Not used for Playwright
            failfast: Stop on first failure
            verbose: Not used for Playwright
            timeout: Not used (Playwright has its own timeout config)

        Returns:
            List of command arguments (e.g., ['npx', 'playwright', 'test', ...])
        """
        cmd = self._build_base_command()

        # Use JSON reporter for structured output
        cmd.extend(["--reporter=json"])

        if failfast:
            cmd.append("--max-failures=1")

        if parallel:
            cmd.extend(["--workers", "auto"])
        else:
            cmd.extend(["--workers", "1"])

        # Add specific test files if provided
        if tests:
            for test in tests:
                if test.path:
                    cmd.append(test.path)

        return cmd

    def _parse_results(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration: float,
    ) -> TestResult:
        """Parse Playwright JSON reporter output."""
        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        failures: List[TestFailure] = []

        try:
            # Try to parse JSON output
            data = json.loads(stdout)

            # Extract stats
            stats = data.get("stats", {})
            passed = stats.get("expected", 0)
            failed = stats.get("unexpected", 0)
            skipped = stats.get("skipped", 0)
            errors = stats.get("flaky", 0)  # Treat flaky as errors

            # Extract failure details
            for suite in data.get("suites", []):
                failures.extend(self._extract_failures_from_suite(suite))

            return TestResult(
                passed=passed,
                failed=failed,
                errors=errors,
                skipped=skipped,
                duration=duration,
                exit_code=exit_code,
                failures=failures,
                parsed_from="playwright",
            )

        except json.JSONDecodeError:
            # Fall back to exit code based result
            logger.warning("Could not parse Playwright JSON output, using exit code")

            if exit_code == 0:
                passed = 1
            else:
                failed = 1
                failures.append(TestFailure(
                    test_id="unknown",
                    test_name="Playwright Tests",
                    message=stderr or stdout or "Tests failed",
                ))

            return TestResult(
                passed=passed,
                failed=failed,
                errors=errors,
                skipped=skipped,
                duration=duration,
                exit_code=exit_code,
                failures=failures,
                parsed_from="fallback",
                parsing_warning="Could not parse Playwright JSON output",
            )

    def _extract_failures_from_suite(self, suite: Dict[str, Any]) -> List[TestFailure]:
        """Extract failure details from suite results."""
        failures = []

        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    status = result.get("status", "")
                    if status in ("failed", "timedOut", "interrupted"):
                        error = result.get("error", {})
                        failures.append(TestFailure(
                            test_id=spec.get("id", spec.get("title", "")),
                            test_name=spec.get("title", ""),
                            message=error.get("message", f"Test {status}"),
                            traceback=error.get("stack"),
                            duration=result.get("duration", 0) / 1000,  # Convert ms to seconds
                        ))

        # Recurse into child suites
        for child_suite in suite.get("suites", []):
            failures.extend(self._extract_failures_from_suite(child_suite))

        return failures

    def get_available_markers(self) -> List[str]:
        """Return available test markers/tags."""
        return ["browser", "e2e", "visual", "smoke"]

    def validate_environment(self) -> bool:
        """Validate Playwright is installed and configured."""
        # Check npx is available
        try:
            self._get_npx_path()
        except RuntimeError:
            return False

        # Check playwright config exists
        config_path = Path(self.project_root) / self.config_file
        if not config_path.exists():
            # Try common alternative names
            alternatives = ["playwright.config.js", "playwright.config.mjs"]
            for alt in alternatives:
                if (Path(self.project_root) / alt).exists():
                    self.config_file = alt
                    return True
            logger.warning(f"Playwright config not found at {config_path}")
            return False

        return True
