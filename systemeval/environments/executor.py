"""
Flexible test executor for running various test commands and scripts.

Supports:
- Shell scripts (./scripts/run-e2e.sh)
- Multi-step command sequences
- Pytest/Jest with custom arguments
- Arbitrary shell commands
- Docker exec commands
"""
import json
import os
import re
import select
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from systemeval.adapters import TestResult
from systemeval.utils.logging import get_logger

logger = get_logger(__name__)


# Compiled regex patterns for test output parsing
# These are compiled once at module load for better performance

# Pytest patterns - multiple formats for robustness
# This pattern matches the decorated summary line like:
# "============ 10 passed, 1 failed, 1 error in 5.23s ============"
# It requires at least one test count to be present (passed|failed|error|skipped)
PYTEST_FULL_PATTERN = re.compile(
    r"=+\s+"  # Leading equals followed by whitespace (required)
    r"(?:"  # Start of required test counts group
    r"(?:(?P<warnings>\d+)\s+warnings?,?\s*)?"  # Optional warnings
    r"(?:(?P<passed>\d+)\s+passed(?:,\s*|\s+))?"  # Passed count
    r"(?:(?P<failed>\d+)\s+failed(?:,\s*|\s+))?"  # Failed count
    r"(?:(?P<errors>\d+)\s+errors?(?:,\s*|\s+))?"  # Error count
    r"(?:(?P<skipped>\d+)\s+skipped(?:,\s*|\s+))?"  # Skipped count
    r"(?:(?P<deselected>\d+)\s+deselected(?:,\s*|\s+))?"  # Deselected count
    r")"
    r"(?:in\s+(?P<duration>[\d.]+)s?)?"  # Duration
    r"\s*=+",  # Trailing equals
    re.IGNORECASE
)

# Alternative pytest summary line (without equals decoration)
PYTEST_SHORT_SUMMARY = re.compile(
    r"(?P<passed>\d+)\s+passed"
    r"(?:,\s*(?P<failed>\d+)\s+failed)?"
    r"(?:,\s*(?P<errors>\d+)\s+errors?)?"
    r"(?:,\s*(?P<skipped>\d+)\s+skipped)?"
    r"(?:\s+in\s+(?P<duration>[\d.]+)s)?",
    re.IGNORECASE
)

# Pytest collection errors
PYTEST_COLLECTION_ERROR = re.compile(
    r"(?:collected\s+0\s+items|no\s+tests\s+ran|"
    r"ERROR\s+collecting|collection\s+error|"
    r"ModuleNotFoundError|ImportError)",
    re.IGNORECASE
)

# Jest patterns - handles "5 passed, 0 failed" or "0 failed, 5 passed" ordering
JEST_SUMMARY = re.compile(
    r"Tests?:\s*"
    r"(?:(?P<passed>\d+)\s+passed,?\s*)?"
    r"(?:(?P<failed>\d+)\s+failed,?\s*)?"
    r"(?:(?P<skipped>\d+)\s+(?:skipped|todo),?\s*)?"
    r"(?P<total>\d+)\s+total",
    re.IGNORECASE
)

JEST_TIME = re.compile(r"Time:\s*([\d.]+)\s*s", re.IGNORECASE)

# Playwright patterns - requires parentheses around duration like "5 passed (10s)"
# This distinguishes from pytest's "5 passed in 1.0s" format
PLAYWRIGHT_SUMMARY = re.compile(
    r"(?P<passed>\d+)\s+passed\s*\(\s*(?P<duration>[\d.]+)\s*(?:s|ms)\s*\)",
    re.IGNORECASE
)

PLAYWRIGHT_FAILED = re.compile(
    r"(?P<failed>\d+)\s+(?:failed|flaky)",
    re.IGNORECASE
)

PLAYWRIGHT_SKIPPED = re.compile(
    r"(?P<skipped>\d+)\s+skipped",
    re.IGNORECASE
)

# Mocha patterns
MOCHA_PASSING = re.compile(r"(\d+)\s+passing\s*\(([^)]+)\)", re.IGNORECASE)
MOCHA_FAILING = re.compile(r"(\d+)\s+failing", re.IGNORECASE)
MOCHA_PENDING = re.compile(r"(\d+)\s+pending", re.IGNORECASE)

# Go test patterns - allow optional leading whitespace
GO_TEST_PASS = re.compile(r"^\s*ok\s+\S+\s+([\d.]+)s", re.MULTILINE)
GO_TEST_FAIL = re.compile(r"^\s*FAIL\s+\S+", re.MULTILINE)
GO_TEST_SKIP = re.compile(r"^\s*\?\s+\S+\s+\[no test files\]", re.MULTILINE)

# Generic patterns for counting individual test results
INDIVIDUAL_PASSED = re.compile(r"(\d+)\s+(?:passed|passing|succeeded|ok)\b", re.IGNORECASE)
INDIVIDUAL_FAILED = re.compile(r"(\d+)\s+(?:failed|failing|failure|errors?)\b", re.IGNORECASE)
INDIVIDUAL_SKIPPED = re.compile(r"(\d+)\s+(?:skipped|pending|ignored)\b", re.IGNORECASE)
DURATION_PATTERN = re.compile(r"(?:in|time[:\s]*)\s*([\d.]+)\s*s(?:econds?)?", re.IGNORECASE)


@dataclass
class ExecutionConfig:
    """Configuration for test execution."""
    command: Union[str, List[str]]  # Single command or list of commands
    working_dir: str = "."
    env: Dict[str, str] = field(default_factory=dict)
    timeout: Optional[int] = None
    shell: bool = True  # Use shell for command interpretation
    stream_output: bool = True
    capture_output: bool = True
    fail_fast: bool = True  # Stop on first command failure


@dataclass
class ExecutionResult:
    """Result of test execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    command: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class TestExecutor:
    """
    Flexible executor for running test commands.

    Handles various test scenarios:
    - Simple commands: "pytest -v"
    - Shell scripts: "./scripts/run-e2e.sh"
    - Multi-step: ["npm run build", "npm test", "./scripts/validate.sh"]
    - Complex pipelines: "cd app && npm install && npm test"
    """

    def __init__(
        self,
        working_dir: str = ".",
        env: Optional[Dict[str, str]] = None,
        verbose: bool = False,
    ) -> None:
        self.working_dir = Path(working_dir)
        self.base_env = env or {}
        self.verbose = verbose
        self._output_buffer: List[str] = []

    def execute(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        stream: bool = True,
        shell: bool = True,
    ) -> ExecutionResult:
        """
        Execute a test command or script.

        Args:
            command: Command string, script path, or list of commands
            timeout: Timeout in seconds
            env: Additional environment variables
            stream: Stream output in real-time
            shell: Use shell for command interpretation

        Returns:
            ExecutionResult with output and exit code
        """
        # Handle list of commands
        if isinstance(command, list):
            return self._execute_sequence(command, timeout, env, stream, shell)

        # Single command
        return self._execute_single(command, timeout, env, stream, shell)

    def _execute_single(
        self,
        command: str,
        timeout: Optional[int],
        env: Optional[Dict[str, str]],
        stream: bool,
        shell: bool,
    ) -> ExecutionResult:
        """Execute a single command."""
        logger.debug(f"Executing command: {command[:100]}{'...' if len(command) > 100 else ''}")
        start = time.time()

        # Build environment
        full_env = dict(os.environ)
        full_env.update(self.base_env)
        if env:
            full_env.update(env)

        # Ensure working directory exists
        if not self.working_dir.exists():
            logger.error(f"Working directory does not exist: {self.working_dir}")
            return ExecutionResult(
                exit_code=2,
                stdout="",
                stderr=f"Working directory does not exist: {self.working_dir}",
                duration=0.0,
                command=command,
            )

        try:
            if stream:
                return self._execute_streaming(command, timeout, full_env, shell, start)
            else:
                return self._execute_capture(command, timeout, full_env, shell, start)
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out after {timeout}s: {command[:50]}...")
            return ExecutionResult(
                exit_code=124,
                stdout="\n".join(self._output_buffer),
                stderr=f"Command timed out after {timeout}s",
                duration=time.time() - start,
                command=command,
            )
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration=time.time() - start,
                command=command,
            )

    def _execute_streaming(
        self,
        command: str,
        timeout: Optional[int],
        env: Dict[str, str],
        shell: bool,
        start: float,
    ) -> ExecutionResult:
        """Execute with real-time output streaming and timeout enforcement."""
        self._output_buffer = []

        process = subprocess.Popen(
            command if shell else shlex.split(command),
            shell=shell,
            cwd=self.working_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output with timeout enforcement using select
        try:
            self._stream_with_timeout(process, timeout, start)
        except TimeoutError:
            # Kill the process on timeout
            process.kill()
            try:
                process.wait(timeout=5)  # Give it 5 seconds to die gracefully
            except subprocess.TimeoutExpired:
                process.terminate()  # Force kill if still alive

            return ExecutionResult(
                exit_code=124,
                stdout="".join(self._output_buffer),
                stderr=f"Command timed out after {timeout}s",
                duration=time.time() - start,
                command=command,
            )

        # Wait for process to complete (should be immediate since we already read all output)
        process.wait()

        return ExecutionResult(
            exit_code=process.returncode,
            stdout="".join(self._output_buffer),
            stderr="",
            duration=time.time() - start,
            command=command,
        )

    def _stream_with_timeout(
        self,
        process: subprocess.Popen,
        timeout: Optional[int],
        start: float,
    ) -> None:
        """
        Stream process output with timeout enforcement using select.

        Raises:
            TimeoutError: If timeout is exceeded
        """
        if timeout is None:
            # No timeout - use simple blocking read
            for line in iter(process.stdout.readline, ""):
                if self.verbose:
                    print(line, end="")
                self._output_buffer.append(line)
            return

        # Use select for non-blocking I/O with timeout
        end_time = start + timeout

        while True:
            # Check if we've exceeded timeout
            remaining = end_time - time.time()
            if remaining <= 0:
                raise TimeoutError(f"Command exceeded timeout of {timeout}s")

            # Check if process has terminated
            if process.poll() is not None:
                # Process finished - read any remaining output
                remaining_output = process.stdout.read()
                if remaining_output:
                    for line in remaining_output.splitlines(keepends=True):
                        if self.verbose:
                            print(line, end="")
                        self._output_buffer.append(line)
                break

            # Wait for data with timeout using select
            # select.select() works on Unix/macOS for file descriptors
            try:
                ready, _, _ = select.select([process.stdout], [], [], min(remaining, 0.1))
            except (ValueError, OSError):
                # File descriptor might be closed or invalid
                break

            if ready:
                # Data is available - read one line
                line = process.stdout.readline()
                if not line:
                    # EOF reached
                    break
                if self.verbose:
                    print(line, end="")
                self._output_buffer.append(line)
            # If not ready, loop continues and will check timeout again

    def _execute_capture(
        self,
        command: str,
        timeout: Optional[int],
        env: Dict[str, str],
        shell: bool,
        start: float,
    ) -> ExecutionResult:
        """Execute with output capture (no streaming)."""
        result = subprocess.run(
            command if shell else shlex.split(command),
            shell=shell,
            cwd=self.working_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration=time.time() - start,
            command=command,
        )

    def _execute_sequence(
        self,
        commands: List[str],
        timeout: Optional[int],
        env: Optional[Dict[str, str]],
        stream: bool,
        shell: bool,
    ) -> ExecutionResult:
        """Execute a sequence of commands, stopping on first failure."""
        all_stdout = []
        all_stderr = []
        total_duration = 0.0

        for cmd in commands:
            result = self._execute_single(cmd, timeout, env, stream, shell)
            all_stdout.append(f"=== {cmd} ===\n{result.stdout}")
            if result.stderr:
                all_stderr.append(f"=== {cmd} ===\n{result.stderr}")
            total_duration += result.duration

            if not result.success:
                return ExecutionResult(
                    exit_code=result.exit_code,
                    stdout="\n".join(all_stdout),
                    stderr="\n".join(all_stderr),
                    duration=total_duration,
                    command=" && ".join(commands),
                )

        return ExecutionResult(
            exit_code=0,
            stdout="\n".join(all_stdout),
            stderr="\n".join(all_stderr),
            duration=total_duration,
            command=" && ".join(commands),
        )

    def parse_test_results(
        self,
        output: str,
        exit_code: int,
        json_output: Optional[str] = None,
    ) -> TestResult:
        """
        Parse test output to extract results.

        Parsing priority:
        1. Structured JSON output (pytest-json-report, jest --json)
        2. Framework-specific regex patterns (pytest, jest, playwright, mocha, go)
        3. Generic patterns
        4. Fallback based on exit code (with warning)

        Args:
            output: Test command stdout/stderr
            exit_code: Command exit code
            json_output: Optional JSON output from structured reporters

        Returns:
            TestResult with parsed counts and metadata
        """
        # Try structured JSON output first (most reliable)
        if json_output:
            result = self._parse_json_output(json_output, exit_code)
            if result:
                return result

        # Look for embedded JSON in output (some reporters embed it)
        json_result = self._extract_embedded_json(output, exit_code)
        if json_result:
            return json_result

        # Try framework-specific parsers in order of specificity
        # More specific patterns (Jest "Tests:", Go "ok\s+\S+") should come first
        # to avoid false matches by generic patterns
        parsers = [
            ("jest", self._parse_jest_output),  # Has specific "Tests:" prefix
            ("go", self._parse_go_output),  # Has specific "ok" at line start
            ("mocha", self._parse_mocha_output),  # Has specific "passing (" format
            ("playwright", self._parse_playwright_output),  # Has specific "passed (Xs)" format
            ("pytest", self._parse_pytest_output),  # Has decorated lines or simple format
            ("generic", self._parse_generic_output),  # Fallback patterns
        ]

        for parser_name, parser_func in parsers:
            result = parser_func(output, exit_code)
            if result:
                result.parsed_from = parser_name
                return result

        # Fallback: couldn't parse output
        return self._create_fallback_result(output, exit_code)

    def _parse_json_output(
        self,
        json_output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Parse structured JSON output from test reporters."""
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError:
            return None

        # pytest-json-report format
        if "summary" in data and "tests" in data:
            summary = data.get("summary", {})
            return TestResult(
                passed=summary.get("passed", 0),
                failed=summary.get("failed", 0),
                errors=summary.get("error", 0),
                skipped=summary.get("skipped", 0),
                duration=data.get("duration", 0.0),
                exit_code=exit_code,
                parsed_from="json:pytest",
            )

        # Jest JSON format
        if "numPassedTests" in data:
            return TestResult(
                passed=data.get("numPassedTests", 0),
                failed=data.get("numFailedTests", 0),
                errors=0,
                skipped=data.get("numPendingTests", 0),
                duration=data.get("testResults", [{}])[0].get("perfStats", {}).get("runtime", 0) / 1000,
                exit_code=exit_code,
                parsed_from="json:jest",
            )

        # Playwright JSON format
        if "stats" in data and "expected" in data.get("stats", {}):
            stats = data["stats"]
            return TestResult(
                passed=stats.get("expected", 0),
                failed=stats.get("unexpected", 0),
                errors=0,
                skipped=stats.get("skipped", 0),
                duration=stats.get("duration", 0) / 1000,  # ms to seconds
                exit_code=exit_code,
                parsed_from="json:playwright",
            )

        return None

    def _extract_embedded_json(
        self,
        output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Extract and parse embedded JSON from output."""
        # Look for common JSON patterns in output
        json_patterns = [
            # pytest-json-report inline
            r'\{[^{}]*"summary"\s*:\s*\{[^}]+\}[^{}]*\}',
            # Jest JSON output
            r'\{[^{}]*"numPassedTests"\s*:\s*\d+[^{}]*\}',
        ]

        for pattern in json_patterns:
            match = re.search(pattern, output)
            if match:
                result = self._parse_json_output(match.group(0), exit_code)
                if result:
                    return result

        return None

    def _parse_pytest_output(
        self,
        output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Parse pytest output format."""
        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        duration = 0.0
        found = False

        # Try the full decorated summary line first
        match = PYTEST_FULL_PATTERN.search(output)
        if match:
            groups = match.groupdict()
            passed = int(groups.get("passed") or 0)
            failed = int(groups.get("failed") or 0)
            errors = int(groups.get("errors") or 0)
            skipped = int(groups.get("skipped") or 0)
            if groups.get("duration"):
                duration = float(groups["duration"])
            found = True
        else:
            # Try the short summary format
            match = PYTEST_SHORT_SUMMARY.search(output)
            if match:
                groups = match.groupdict()
                passed = int(groups.get("passed") or 0)
                failed = int(groups.get("failed") or 0)
                errors = int(groups.get("errors") or 0)
                skipped = int(groups.get("skipped") or 0)
                if groups.get("duration"):
                    duration = float(groups["duration"])
                found = True

        # Check for collection errors
        if PYTEST_COLLECTION_ERROR.search(output):
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=duration,
                exit_code=exit_code,
                parsed_from="pytest",
                parsing_warning="Collection error detected",
            )

        if not found:
            return None

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
        )

    def _parse_jest_output(
        self,
        output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Parse Jest output format."""
        match = JEST_SUMMARY.search(output)
        if not match:
            return None

        groups = match.groupdict()
        passed = int(groups.get("passed") or 0)
        failed = int(groups.get("failed") or 0)
        skipped = int(groups.get("skipped") or 0)

        duration = 0.0
        time_match = JEST_TIME.search(output)
        if time_match:
            duration = float(time_match.group(1))

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
        )

    def _parse_playwright_output(
        self,
        output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Parse Playwright output format."""
        match = PLAYWRIGHT_SUMMARY.search(output)
        if not match:
            return None

        groups = match.groupdict()
        passed = int(groups.get("passed") or 0)
        duration = 0.0
        if groups.get("duration"):
            dur_str = groups["duration"]
            # Handle both seconds and milliseconds
            dur_val = float(dur_str)
            # If duration > 1000, assume milliseconds
            duration = dur_val / 1000 if dur_val > 1000 else dur_val

        failed = 0
        failed_match = PLAYWRIGHT_FAILED.search(output)
        if failed_match:
            failed = int(failed_match.group("failed"))

        skipped = 0
        skipped_match = PLAYWRIGHT_SKIPPED.search(output)
        if skipped_match:
            skipped = int(skipped_match.group("skipped"))

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
        )

    def _parse_mocha_output(
        self,
        output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Parse Mocha output format."""
        passing_match = MOCHA_PASSING.search(output)
        if not passing_match:
            return None

        passed = int(passing_match.group(1))
        duration_str = passing_match.group(2)

        # Parse duration (could be "2s", "500ms", etc.)
        duration = 0.0
        if "ms" in duration_str:
            duration = float(duration_str.replace("ms", "").strip()) / 1000
        elif "s" in duration_str:
            duration = float(duration_str.replace("s", "").strip())

        failed = 0
        failing_match = MOCHA_FAILING.search(output)
        if failing_match:
            failed = int(failing_match.group(1))

        skipped = 0
        pending_match = MOCHA_PENDING.search(output)
        if pending_match:
            skipped = int(pending_match.group(1))

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
        )

    def _parse_go_output(
        self,
        output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Parse Go test output format."""
        pass_matches = GO_TEST_PASS.findall(output)
        fail_matches = GO_TEST_FAIL.findall(output)
        skip_matches = GO_TEST_SKIP.findall(output)

        if not pass_matches and not fail_matches:
            return None

        passed = len(pass_matches)
        failed = len(fail_matches)
        skipped = len(skip_matches)

        # Sum up durations from all passing packages
        duration = sum(float(d) for d in pass_matches)

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
        )

    def _parse_generic_output(
        self,
        output: str,
        exit_code: int,
    ) -> Optional[TestResult]:
        """Parse output using generic patterns as last resort."""
        passed = 0
        failed = 0
        skipped = 0
        duration = 0.0
        found = False

        # Look for passed counts
        passed_matches = INDIVIDUAL_PASSED.findall(output)
        if passed_matches:
            # Take the largest number found (usually the total)
            passed = max(int(m) for m in passed_matches)
            found = True

        # Look for failed counts
        failed_matches = INDIVIDUAL_FAILED.findall(output)
        if failed_matches:
            failed = max(int(m) for m in failed_matches)
            found = True

        # Look for skipped counts
        skipped_matches = INDIVIDUAL_SKIPPED.findall(output)
        if skipped_matches:
            skipped = max(int(m) for m in skipped_matches)
            found = True

        # Look for duration
        duration_match = DURATION_PATTERN.search(output)
        if duration_match:
            duration = float(duration_match.group(1))

        if not found:
            return None

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
        )

    def _create_fallback_result(
        self,
        output: str,
        exit_code: int,
    ) -> TestResult:
        """
        Create a fallback result when output cannot be parsed.

        When exit_code == 0 but output is unrecognized:
        - Assume 1 passed with a warning

        When exit_code != 0 and output is unrecognized:
        - Set errors=1 (not failed) to trigger ERROR verdict
        - This prevents false positives from guessed test counts
        """
        if exit_code == 0:
            return TestResult(
                passed=1,
                failed=0,
                errors=0,
                skipped=0,
                duration=0.0,
                exit_code=exit_code,
                parsed_from="fallback",
                parsing_warning=(
                    "Output format not recognized. "
                    "Assumed 1 test passed based on exit code 0. "
                    "Consider using structured output (--json-report for pytest, --json for jest)."
                ),
            )
        else:
            # Non-zero exit code with unrecognized output -> ERROR, not FAIL
            return TestResult(
                passed=0,
                failed=0,
                errors=1,  # This triggers ERROR verdict in TestResult.verdict
                skipped=0,
                duration=0.0,
                exit_code=exit_code,
                parsed_from="fallback",
                parsing_warning=(
                    f"Output format not recognized and command failed (exit code {exit_code}). "
                    "Cannot determine actual test counts. Reporting as ERROR. "
                    "Consider using structured output (--json-report for pytest, --json for jest)."
                ),
            )


class DockerExecutor(TestExecutor):
    """
    Executor for running commands inside Docker containers.
    """

    def __init__(
        self,
        container: str,
        compose_file: str = "docker-compose.yml",
        project_dir: str = ".",
        project_name: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(working_dir=project_dir, verbose=verbose)
        self.container = container
        self.compose_file = compose_file
        self.project_name = project_name

    def execute(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        stream: bool = True,
        shell: bool = True,
    ) -> ExecutionResult:
        """Execute command inside Docker container."""
        # Handle list of commands
        if isinstance(command, list):
            results = []
            for cmd in command:
                result = self._docker_exec(cmd, timeout, env, stream)
                results.append(result)
                if not result.success:
                    break

            # Aggregate results
            return ExecutionResult(
                exit_code=results[-1].exit_code if results else 0,
                stdout="\n".join(r.stdout for r in results),
                stderr="\n".join(r.stderr for r in results if r.stderr),
                duration=sum(r.duration for r in results),
                command=" && ".join(command),
            )

        return self._docker_exec(command, timeout, env, stream)

    def _docker_exec(
        self,
        command: str,
        timeout: Optional[int],
        env: Optional[Dict[str, str]],
        stream: bool,
    ) -> ExecutionResult:
        """Execute a single command via docker compose exec."""
        logger.debug(f"Executing in Docker container '{self.container}': {command[:100]}...")
        start = time.time()

        # Build docker compose exec command
        docker_cmd = ["docker", "compose", "-f", self.compose_file]
        if self.project_name:
            docker_cmd.extend(["-p", self.project_name])
        docker_cmd.extend(["exec", "-T"])  # -T disables pseudo-TTY

        # Add environment variables
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])

        docker_cmd.append(self.container)
        docker_cmd.extend(["sh", "-c", command])

        try:
            if stream:
                process = subprocess.Popen(
                    docker_cmd,
                    cwd=self.working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                # Use parent class's timeout-aware streaming
                self._output_buffer = []
                try:
                    self._stream_with_timeout(process, timeout, start)
                except TimeoutError:
                    # Kill the process on timeout
                    process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()

                    return ExecutionResult(
                        exit_code=124,
                        stdout="".join(self._output_buffer),
                        stderr=f"Command timed out after {timeout}s",
                        duration=time.time() - start,
                        command=command,
                    )

                process.wait()

                return ExecutionResult(
                    exit_code=process.returncode,
                    stdout="".join(self._output_buffer),
                    stderr="",
                    duration=time.time() - start,
                    command=command,
                )
            else:
                result = subprocess.run(
                    docker_cmd,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                return ExecutionResult(
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    duration=time.time() - start,
                    command=command,
                )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                exit_code=124,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration=time.time() - start,
                command=command,
            )
        except Exception as e:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration=time.time() - start,
                command=command,
            )
