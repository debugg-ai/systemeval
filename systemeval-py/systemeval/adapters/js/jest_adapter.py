"""
Jest adapter for TypeScript/JavaScript testing.

Runs Jest tests via npx and parses JSON output for results.
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


class JestAdapter(BaseJavaScriptAdapter):
    """
    Adapter for running Jest tests.

    Uses npx jest to execute tests and parses JSON output for results.

    Supports initialization with either AdapterConfig or legacy parameters.

    Example:
        # Using AdapterConfig (preferred)
        config = AdapterConfig(
            project_root="/path/to/project",
            timeout=60,
            extra={
                "config_file": "jest.config.js",
                "coverage": True,
            }
        )
        adapter = JestAdapter(config)

        # Using legacy parameters (backward compatible)
        adapter = JestAdapter(
            project_root="/path/to/project",
            config_file="jest.config.js",
        )
    """

    def __init__(
        self,
        config_or_project_root: Union[AdapterConfig, str, Path],
        config_file: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        """Initialize Jest adapter.

        Args:
            config_or_project_root: Either an AdapterConfig object or project root path.
            config_file: Path to jest config (jest.config.js, jest.config.ts, etc.).
            timeout: Default timeout in seconds.
        """
        super().__init__(config_or_project_root)

        # Extract Jest-specific settings from config or use legacy params
        if isinstance(config_or_project_root, AdapterConfig):
            self.config_file = self.config.get("config_file", None)
            self.timeout = self.config.timeout or self.config.get("timeout", 60)
        else:
            # Legacy initialization
            self.config_file = config_file
            self.timeout = timeout

    def _build_base_command(self) -> List[str]:
        """Build base jest command."""
        cmd = [self._get_npx_path(), "jest"]

        if self.config_file:
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
        """Discover Jest tests using --listTests flag."""
        cmd = self._build_base_command()
        cmd.extend(["--listTests", "--json"])

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

            # Parse JSON output - Jest returns array of test file paths
            tests = []
            if result.stdout:
                try:
                    # Jest --listTests --json returns array of file paths
                    data = json.loads(result.stdout)
                    if isinstance(data, list):
                        for test_file in data:
                            tests.append(TestItem(
                                id=test_file,
                                name=Path(test_file).name,
                                path=test_file,
                                markers=["jest", "unit"],
                            ))
                except json.JSONDecodeError:
                    # Try line-by-line parsing
                    for line in result.stdout.strip().split("\n"):
                        if line.strip() and line.strip().endswith((".js", ".ts", ".jsx", ".tsx")):
                            tests.append(TestItem(
                                id=line.strip(),
                                name=Path(line.strip()).name,
                                path=line.strip(),
                                markers=["jest", "unit"],
                            ))

            return tests

        except subprocess.TimeoutExpired:
            logger.error("Test discovery timed out")
            return []
        except FileNotFoundError:
            logger.error("npx or jest not found")
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
        """Execute Jest tests and return structured results.

        Runs Jest via npx with JSON reporter and parses the output into
        a unified TestResult format.

        Args:
            tests: Optional list of specific test files to run.
                   If None, runs all tests discovered by Jest.
            parallel: Enable parallel execution (Jest default). Set to False
                      to use --runInBand for serial execution.
            coverage: Enable coverage collection via --coverage flag.
            failfast: Stop on first failure via --bail flag.
            verbose: Enable verbose output via --verbose flag.
            timeout: Maximum execution time in seconds. Defaults to adapter's
                     configured timeout. Subprocess is killed after timeout.

        Returns:
            TestResult with parsed Jest results including:
            - Test counts from numPassedTests/numFailedTests
            - Failure details from assertionResults
            - Duration and exit code

        Note:
            Jest runs in parallel by default. Set parallel=False to disable.
            If JSON parsing fails, falls back to exit-code-based result.
        """
        start_time = time.time()
        cmd = self._build_base_command()

        # Use JSON reporter for structured output
        cmd.append("--json")

        if coverage:
            cmd.append("--coverage")

        if failfast:
            cmd.append("--bail")

        if verbose:
            cmd.append("--verbose")

        # Jest runs in parallel by default, use --runInBand to disable
        if not parallel:
            cmd.append("--runInBand")

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
                    message="npx or jest not found in PATH",
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
        """Get the Jest command that would be used to run tests.

        Args:
            tests: Specific test items to run (None = run all)
            parallel: Enable parallel test execution (default in Jest)
            coverage: Enable coverage collection
            failfast: Stop on first failure (--bail)
            verbose: Enable verbose output
            timeout: Not used (Jest has its own timeout config)

        Returns:
            List of command arguments (e.g., ['npx', 'jest', ...])
        """
        cmd = self._build_base_command()

        # Use JSON reporter for structured output
        cmd.append("--json")

        if coverage:
            cmd.append("--coverage")

        if failfast:
            cmd.append("--bail")

        if verbose:
            cmd.append("--verbose")

        if not parallel:
            cmd.append("--runInBand")

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
        """Parse Jest JSON output."""
        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        failures: List[TestFailure] = []

        try:
            # Try to parse JSON output
            data = json.loads(stdout)

            # Extract stats from Jest JSON format
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
                            traceback=message,  # Jest includes stack in failure message
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
                parsed_from="jest",
            )

        except json.JSONDecodeError:
            # Fall back to exit code based result
            logger.warning("Could not parse Jest JSON output, using exit code")

            if exit_code == 0:
                passed = 1
            else:
                failed = 1
                # Try to extract error from stderr
                error_msg = stderr.strip() if stderr else stdout.strip() if stdout else "Tests failed"
                failures.append(TestFailure(
                    test_id="unknown",
                    test_name="Jest Tests",
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
                parsing_warning="Could not parse Jest JSON output",
            )

    def get_available_markers(self) -> List[str]:
        """Return available test markers/tags."""
        return ["jest", "unit", "integration", "snapshot"]

    def validate_environment(self) -> bool:
        """Validate Jest is installed and configured."""
        # Check npx is available
        try:
            self._get_npx_path()
        except RuntimeError:
            return False

        # Check jest config exists (optional - Jest can work without explicit config)
        if self.config_file:
            config_path = Path(self.project_root) / self.config_file
            if not config_path.exists():
                logger.warning(f"Jest config not found at {config_path}")
                # Still return True as Jest can work without config
                return True
        else:
            # Try to find common config files
            common_configs = [
                "jest.config.js",
                "jest.config.ts",
                "jest.config.mjs",
                "jest.config.cjs",
            ]
            for config in common_configs:
                if (Path(self.project_root) / config).exists():
                    self.config_file = config
                    return True

            # Check package.json for jest config
            package_json = Path(self.project_root) / "package.json"
            if package_json.exists():
                try:
                    with open(package_json) as f:
                        pkg = json.load(f)
                        if "jest" in pkg:
                            return True
                except (json.JSONDecodeError, IOError):
                    pass

        return True
