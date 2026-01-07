"""
Standalone environment for simple process-based testing.

Used for Next.js dev servers, direct pytest runs, etc.
Supports flexible test execution including custom scripts.
"""
import logging
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

from systemeval.types import TestResult
from systemeval.environments.base import Environment, EnvironmentType, SetupResult
from systemeval.environments.executor import TestExecutor
from systemeval.utils.commands import build_test_command


class StandaloneEnvironment(Environment):
    """
    Environment for standalone processes (no Docker).

    Starts a process, waits for ready pattern, runs tests, stops process.
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name, config)
        self._process: Optional[subprocess.Popen] = None
        self._output_buffer: List[str] = []

        # Extract config
        self.command = config.get("command", "")
        self.ready_pattern = config.get("ready_pattern", "")
        self.test_command = config.get("test_command", "")
        self.port = config.get("port", 3000)
        self.working_dir = Path(config.get("working_dir", "."))
        self.env_vars = config.get("env", {})

    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.STANDALONE

    def setup(self) -> SetupResult:
        """Start the standalone process."""
        if not self.command:
            return SetupResult(
                success=True,
                message="No command configured, skipping startup",
            )

        start = time.time()

        try:
            # Build environment
            env = dict(os.environ)
            env.update(self.env_vars)

            # Parse command
            cmd = shlex.split(self.command)

            # Start process
            self._process = subprocess.Popen(
                cmd,
                cwd=self.working_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            self.timings.startup = time.time() - start

            return SetupResult(
                success=True,
                message=f"Started: {self.command}",
                duration=self.timings.startup,
                details={"pid": self._process.pid},
            )

        except Exception as e:
            return SetupResult(
                success=False,
                message=f"Failed to start: {e}",
                duration=time.time() - start,
            )

    def is_ready(self) -> bool:
        """Check if process is ready (pattern matched or no pattern required)."""
        if not self.command:
            return True  # No process to wait for

        if not self._process:
            return False

        if self._process.poll() is not None:
            return False  # Process exited

        if not self.ready_pattern:
            return True  # No pattern required

        # Check buffered output for pattern
        pattern = re.compile(self.ready_pattern)
        return any(pattern.search(line) for line in self._output_buffer)

    def wait_ready(self, timeout: int = 120) -> bool:
        """Wait for ready pattern in process output."""
        if not self.command:
            return True

        if not self._process or not self._process.stdout:
            return False

        if not self.ready_pattern:
            # No pattern, just wait a moment for startup
            time.sleep(1)
            return self._process.poll() is None

        start = time.time()
        pattern = re.compile(self.ready_pattern)

        while (time.time() - start) < timeout:
            if self._process.poll() is not None:
                # Process exited
                return False

            # Read available output (non-blocking would be better but this works)
            line = self._process.stdout.readline()
            if line:
                self._output_buffer.append(line)
                if pattern.search(line):
                    self.timings.health_check = time.time() - start
                    return True

            time.sleep(0.1)

        return False

    def run_tests(
        self,
        suite: Optional[str] = None,
        category: Optional[str] = None,
        verbose: bool = False,
    ) -> TestResult:
        """
        Run tests using the configured test command.

        Supports:
        - Simple commands: "pytest -v"
        - Shell scripts: "./scripts/run-e2e.sh"
        - Multi-step: ["npm run build", "npm test"]
        - Complex pipelines: "npm install && npm test"
        """
        if not self.test_command:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                exit_code=2,
            )

        start = time.time()

        # Create executor
        executor = TestExecutor(
            working_dir=str(self.working_dir),
            env=self.env_vars,
            verbose=verbose,
        )

        # Build test command with optional filters
        command = self._build_test_command(suite, category, verbose)

        # Execute tests
        result = executor.execute(
            command=command,
            timeout=self.config.get("test_timeout"),
            stream=True,
        )

        self.timings.tests = time.time() - start

        # Parse output to extract test counts
        return executor.parse_test_results(result.stdout, result.exit_code)

    def _build_test_command(
        self,
        suite: Optional[str],
        category: Optional[str],
        verbose: bool,
    ) -> Union[str, List[str]]:
        """Build the test command with optional filters."""
        return build_test_command(self.test_command, suite, category, verbose)

    def teardown(self, keep_running: bool = False) -> None:
        """Stop the standalone process."""
        start = time.time()

        if self._process and not keep_running:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            except OSError as e:
                # Process already terminated or inaccessible
                logger.debug(f"Process cleanup encountered OSError: {e}")
            finally:
                self._process = None

        self.timings.cleanup = time.time() - start
