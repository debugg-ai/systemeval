"""
Docker-based command execution using docker compose exec.

Provides:
- DockerExecutor: Executes commands inside Docker containers
"""
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from systemeval.utils.logging import get_logger
from systemeval.environments.executor.impl.process_executor import ProcessStreamHandler

logger = get_logger(__name__)


class DockerExecutor:
    """
    Executor for running commands inside Docker containers.

    Uses docker compose exec to run commands in containers defined
    by docker-compose.yml. Reuses ProcessStreamHandler for streaming.
    """

    def __init__(
        self,
        container: str,
        compose_file: str = "docker-compose.yml",
        project_dir: str = ".",
        project_name: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        self.container = container
        self.compose_file = compose_file
        self.working_dir = Path(project_dir)
        self.project_name = project_name
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
        """Execute command inside Docker container."""
        from systemeval.environments.executor.models import ExecutionResult

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
    ) -> "ExecutionResult":
        """Execute a single command via docker compose exec."""
        from systemeval.environments.executor.models import ExecutionResult

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

                # Use shared streaming handler with timeout enforcement
                self.stream_handler.clear_buffer()
                try:
                    self.stream_handler.stream_with_timeout(process, timeout, start)
                except TimeoutError:
                    # Kill the process on timeout
                    process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()

                    return ExecutionResult(
                        exit_code=124,
                        stdout=self.stream_handler.get_output(),
                        stderr=f"Command timed out after {timeout}s",
                        duration=time.time() - start,
                        command=command,
                    )

                process.wait()

                return ExecutionResult(
                    exit_code=process.returncode,
                    stdout=self.stream_handler.get_output(),
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

    def parse_test_results(
        self,
        output: str,
        exit_code: int,
        json_output: Optional[str] = None,
    ) -> "TestResult":
        """
        Parse test output to extract results.

        Delegates to test_result_parser module for parsing logic.
        """
        from systemeval.environments.executor.impl.test_result_parser import TestResultAggregator

        aggregator = TestResultAggregator()
        return aggregator.parse(output, exit_code, json_output)
