"""
Process-based command execution with streaming output support.

Provides:
- ProcessStreamHandler: Real-time output streaming with timeout enforcement
- LocalCommandExecutor: Local command execution using subprocess
"""
import os
import select
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from systemeval.utils.logging import get_logger

logger = get_logger(__name__)


class ProcessStreamHandler:
    """
    Handles streaming output from subprocess with timeout enforcement.

    Uses select() for non-blocking I/O on Unix/macOS systems.
    Shared by both LocalCommandExecutor and DockerExecutor.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._output_buffer: List[str] = []

    def stream_with_timeout(
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

    def get_output(self) -> str:
        """Get accumulated output."""
        return "".join(self._output_buffer)

    def clear_buffer(self) -> None:
        """Clear the output buffer."""
        self._output_buffer = []


class LocalCommandExecutor:
    """
    Executor for running commands locally via subprocess.

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
        self.stream_handler = ProcessStreamHandler(verbose=verbose)

    def execute(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        stream: bool = True,
        shell: bool = True,
    ) -> "ExecutionResult":
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
        # Import here to avoid circular dependency
        from systemeval.environments.executor.models import ExecutionResult

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
    ) -> "ExecutionResult":
        """Execute a single command."""
        from systemeval.environments.executor.models import ExecutionResult

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
                stdout=self.stream_handler.get_output(),
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
    ) -> "ExecutionResult":
        """Execute with real-time output streaming and timeout enforcement."""
        from systemeval.environments.executor.models import ExecutionResult

        self.stream_handler.clear_buffer()

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
            self.stream_handler.stream_with_timeout(process, timeout, start)
        except TimeoutError:
            # Kill the process on timeout
            process.kill()
            try:
                process.wait(timeout=5)  # Give it 5 seconds to die gracefully
            except subprocess.TimeoutExpired:
                process.terminate()  # Force kill if still alive

            return ExecutionResult(
                exit_code=124,
                stdout=self.stream_handler.get_output(),
                stderr=f"Command timed out after {timeout}s",
                duration=time.time() - start,
                command=command,
            )

        # Wait for process to complete (should be immediate since we already read all output)
        process.wait()

        return ExecutionResult(
            exit_code=process.returncode,
            stdout=self.stream_handler.get_output(),
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
    ) -> "ExecutionResult":
        """Execute with output capture (no streaming)."""
        from systemeval.environments.executor.models import ExecutionResult

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
    ) -> "ExecutionResult":
        """Execute a sequence of commands, stopping on first failure."""
        from systemeval.environments.executor.models import ExecutionResult

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
