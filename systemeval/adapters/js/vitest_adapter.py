"""
Vitest adapter for TypeScript/JavaScript testing.

Runs Vitest tests via npx and parses JSON output for results.
"""
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from systemeval.adapters.base import AdapterConfig, TestItem, TestResult, TestFailure
from .base import BaseJavaScriptAdapter

logger = logging.getLogger(__name__)


class VitestAdapter(BaseJavaScriptAdapter):
    """
    Adapter for running Vitest tests.

    Uses npx vitest run to execute tests and parses JSON reporter output.

    Supports initialization with either AdapterConfig or legacy parameters.

    Example:
        # Using AdapterConfig (preferred)
        config = AdapterConfig(
            project_root="/path/to/project",
            timeout=60,
            extra={
                "config_file": "vitest.config.ts",
                "coverage": True,
            }
        )
        adapter = VitestAdapter(config)

        # Using legacy parameters (backward compatible)
        adapter = VitestAdapter(
            project_root="/path/to/project",
            config_file="vitest.config.ts",
        )
    """

    def __init__(
        self,
        config_or_project_root: Union[AdapterConfig, str, Path],
        config_file: str = "vitest.config.ts",
        timeout: int = 60,
    ) -> None:
        """Initialize Vitest adapter.

        Args:
            config_or_project_root: Either an AdapterConfig object or project root path.
            config_file: Path to vitest config (vitest.config.ts, vitest.config.js, etc.).
            timeout: Default timeout in seconds.
        """
        super().__init__(config_or_project_root)

        # Extract Vitest-specific settings from config or use legacy params
        if isinstance(config_or_project_root, AdapterConfig):
            self.config_file = self.config.get("config_file", "vitest.config.ts")
            self.timeout = self.config.timeout or self.config.get("timeout", 60)
        else:
            # Legacy initialization
            self.config_file = config_file
            self.timeout = timeout

    def _build_base_command(self) -> List[str]:
        """Build base vitest command."""
        cmd = [self._get_npx_path(), "vitest", "run"]

        config_path = Path(self.project_root) / self.config_file
        if config_path.exists():
            cmd.extend(["--config", str(config_path)])

        return cmd

    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover Vitest tests using --reporter=json flag (Vitest 1.0+)."""
        cmd = self._build_base_command()
        # Use --reporter=json for discovery
        cmd.extend(["--reporter=json", "--passWithNoTests"])

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
                    for test_file in data.get("testResults", []):
                        file_path = test_file.get("name", "")
                        for assertion in test_file.get("assertionResults", []):
                            test_id = assertion.get("fullName", assertion.get("title", ""))
                            ancestors = assertion.get("ancestorTitles", [])
                            suite = " > ".join(ancestors) if ancestors else None

                            tests.append(TestItem(
                                id=test_id,
                                name=assertion.get("title", ""),
                                path=file_path,
                                markers=["vitest", "unit"],
                                metadata={
                                    "suite": suite,
                                    "duration": assertion.get("duration"),
                                },
                                suite=suite,
                            ))
                except json.JSONDecodeError:
                    logger.warning("Could not parse Vitest JSON output for discovery")

            return tests

        except subprocess.TimeoutExpired:
            logger.error("Test discovery timed out")
            return []
        except FileNotFoundError:
            logger.error("npx or vitest not found")
            return []

    def execute(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
    ) -> TestResult:
        """Execute Vitest tests and return structured results.

        Runs Vitest via npx with JSON reporter and parses the output into
        a unified TestResult format.

        Args:
            tests: Optional list of specific test files to run.
                   If None, runs all tests discovered by Vitest.
            parallel: Enable parallel threads (Vitest default). Set to False
                      to use --no-threads for serial execution.
            coverage: Enable coverage collection via --coverage flag.
            failfast: Stop on first failure via --bail flag.
            verbose: Not directly used (Vitest output is JSON).
            timeout: Maximum execution time in seconds. Defaults to adapter's
                     configured timeout. Subprocess is killed after timeout.

        Returns:
            TestResult with parsed Vitest results including:
            - Test counts from numPassedTests/numFailedTests
            - Failure details from assertionResults
            - Duration and exit code

        Note:
            Vitest runs in parallel by default (threads). Set parallel=False
            to disable. Uses JSON reporter format compatible with Jest output.
            If JSON parsing fails, falls back to exit-code-based result.
        """
        start_time = time.time()
        cmd = self._build_base_command()

        # Use JSON reporter for structured output
        cmd.extend(["--reporter=json"])

        if coverage:
            cmd.append("--coverage")

        if failfast:
            cmd.append("--bail")

        # Vitest runs in parallel by default, use --no-threads to disable
        if not parallel:
            cmd.append("--no-threads")

        # Add specific test files if provided
        if tests:
            for test in tests:
                if test.path:
                    cmd.append(test.path)

        # Set timeout
        exec_timeout = timeout or self.timeout

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=exec_timeout,
                env={**os.environ},
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
                    message="npx or vitest not found in PATH",
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
        """Get the Vitest command that would be used to run tests.

        Args:
            tests: Specific test items to run (None = run all)
            parallel: Enable parallel test execution (default in Vitest)
            coverage: Enable coverage collection
            failfast: Stop on first failure (--bail)
            verbose: Enable verbose output
            timeout: Not used (Vitest has its own timeout config)

        Returns:
            List of command arguments (e.g., ['npx', 'vitest', 'run', ...])
        """
        cmd = self._build_base_command()

        # Use JSON reporter for structured output
        cmd.extend(["--reporter=json"])

        if coverage:
            cmd.append("--coverage")

        if failfast:
            cmd.append("--bail")

        if not parallel:
            cmd.append("--no-threads")

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
        """Parse Vitest JSON reporter output."""
        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        failures: List[TestFailure] = []

        try:
            # Try to parse JSON output
            data = json.loads(stdout)

            # Extract stats from Vitest JSON format
            passed = data.get("numPassedTests", 0)
            failed = data.get("numFailedTests", 0)
            skipped = data.get("numPendingTests", 0) + data.get("numTodoTests", 0)

            # Extract failure details
            for test_file in data.get("testResults", []):
                file_path = test_file.get("name", "")
                for assertion in test_file.get("assertionResults", []):
                    status = assertion.get("status", "")
                    if status == "failed":
                        # Get error messages
                        failure_messages = assertion.get("failureMessages", [])
                        message = "\n".join(failure_messages) if failure_messages else "Test failed"

                        failures.append(TestFailure(
                            test_id=assertion.get("fullName", assertion.get("title", "")),
                            test_name=assertion.get("title", ""),
                            message=message,
                            traceback=message,  # Vitest includes stack in failure message
                            duration=(assertion.get("duration") or 0) / 1000,  # Convert ms to seconds
                            metadata={
                                "file": file_path,
                                "suite": " > ".join(assertion.get("ancestorTitles", [])),
                            },
                        ))

            return TestResult(
                passed=passed,
                failed=failed,
                errors=errors,
                skipped=skipped,
                duration=duration,
                exit_code=exit_code,
                failures=failures,
                parsed_from="vitest",
            )

        except json.JSONDecodeError:
            # Fall back to exit code based result
            logger.warning("Could not parse Vitest JSON output, using exit code")

            if exit_code == 0:
                passed = 1
            else:
                failed = 1
                # Try to extract error from stderr
                error_msg = stderr.strip() if stderr else stdout.strip() if stdout else "Tests failed"
                failures.append(TestFailure(
                    test_id="unknown",
                    test_name="Vitest Tests",
                    message=error_msg[:500],  # Truncate long messages
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
                parsing_warning="Could not parse Vitest JSON output",
            )

    def get_available_markers(self) -> List[str]:
        """Return available test markers/tags."""
        return ["vitest", "unit", "integration", "component"]

    def validate_environment(self) -> bool:
        """Validate Vitest is installed and configured."""
        # Check npx is available
        try:
            self._get_npx_path()
        except RuntimeError:
            return False

        # Check vitest config exists
        config_path = Path(self.project_root) / self.config_file
        if not config_path.exists():
            # Try common alternative names
            alternatives = [
                "vitest.config.js",
                "vitest.config.mjs",
                "vitest.config.mts",
                "vite.config.ts",
                "vite.config.js",
            ]
            for alt in alternatives:
                if (Path(self.project_root) / alt).exists():
                    self.config_file = alt
                    return True
            logger.warning(f"Vitest config not found at {config_path}")
            # Still return True as Vitest can work without explicit config
            return True

        return True
