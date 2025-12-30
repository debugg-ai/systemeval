"""
Flexible test executor for running various test commands and scripts.

Supports:
- Shell scripts (./scripts/run-e2e.sh)
- Multi-step command sequences
- Pytest/Jest with custom arguments
- Arbitrary shell commands
- Docker exec commands
"""
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from systemeval.adapters import TestResult


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
        start = time.time()

        # Build environment
        full_env = dict(os.environ)
        full_env.update(self.base_env)
        if env:
            full_env.update(env)

        # Ensure working directory exists
        if not self.working_dir.exists():
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
            return ExecutionResult(
                exit_code=124,
                stdout="\n".join(self._output_buffer),
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

    def _execute_streaming(
        self,
        command: str,
        timeout: Optional[int],
        env: Dict[str, str],
        shell: bool,
        start: float,
    ) -> ExecutionResult:
        """Execute with real-time output streaming."""
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

        # Stream output
        for line in iter(process.stdout.readline, ""):
            if self.verbose:
                print(line, end="")
            self._output_buffer.append(line)

        process.wait(timeout=timeout)

        return ExecutionResult(
            exit_code=process.returncode,
            stdout="".join(self._output_buffer),
            stderr="",
            duration=time.time() - start,
            command=command,
        )

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

    def parse_test_results(self, output: str, exit_code: int) -> TestResult:
        """
        Parse test output to extract results.

        Attempts to detect output format and extract counts.
        Falls back to exit code if parsing fails.
        """
        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        duration = 0.0

        # Try pytest format: "5 passed, 2 failed, 1 error in 12.34s"
        pytest_match = re.search(
            r"(\d+) passed.*?(\d+) failed.*?(\d+) error.*?in ([\d.]+)s",
            output, re.IGNORECASE
        )
        if pytest_match:
            passed = int(pytest_match.group(1))
            failed = int(pytest_match.group(2))
            errors = int(pytest_match.group(3))
            duration = float(pytest_match.group(4))
        else:
            # Try simpler patterns
            if match := re.search(r"(\d+) passed", output):
                passed = int(match.group(1))
            if match := re.search(r"(\d+) failed", output):
                failed = int(match.group(1))
            if match := re.search(r"(\d+) errors?", output):
                errors = int(match.group(1))
            if match := re.search(r"(\d+) skipped", output):
                skipped = int(match.group(1))
            if match := re.search(r"in ([\d.]+)s", output):
                duration = float(match.group(1))

        # Try Jest format: "Tests: 5 passed, 2 failed, 7 total"
        jest_match = re.search(
            r"Tests:\s*(\d+) passed,\s*(\d+) failed,\s*(\d+) total",
            output
        )
        if jest_match:
            passed = int(jest_match.group(1))
            failed = int(jest_match.group(2))

        # Try Playwright format: "5 passed (10s)"
        playwright_match = re.search(r"(\d+) passed.*?\(([\d.]+)s\)", output)
        if playwright_match:
            passed = int(playwright_match.group(1))
            duration = float(playwright_match.group(2))

        # Check for failure patterns in output
        if re.search(r"(\d+) failed", output):
            if match := re.search(r"(\d+) failed", output):
                failed = int(match.group(1))

        # If we couldn't parse anything, use exit code
        if passed == 0 and failed == 0 and errors == 0:
            if exit_code == 0:
                passed = 1  # Assume at least one test passed
            else:
                failed = 1  # Assume at least one test failed

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
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

                output_lines = []
                for line in iter(process.stdout.readline, ""):
                    if self.verbose:
                        print(line, end="")
                    output_lines.append(line)

                process.wait(timeout=timeout)

                return ExecutionResult(
                    exit_code=process.returncode,
                    stdout="".join(output_lines),
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
