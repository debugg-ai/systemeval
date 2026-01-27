"""
Composite environment for multi-environment orchestration.

Combines multiple environments (e.g., backend + frontend for full-stack testing).

USAGE:
    Composite environments enable full-stack testing by orchestrating multiple
    child environments. This is useful for scenarios where you need both backend
    and frontend (or other service combinations) running together.

CONFIGURATION:
    type: composite
    depends_on:
      - backend
      - frontend
    test_command: "npm run e2e:test"

DEPRECATED FEATURES:
    None currently. CompositeEnvironment is actively used for multi-environment
    orchestration and is fully supported.
"""
import time
from typing import Any, Dict, List, Optional

from systemeval.types import TestResult
from systemeval.environments.base import Environment, EnvironmentType, SetupResult


class CompositeEnvironment(Environment):
    """
    Environment that combines multiple child environments.

    Used for full-stack testing where backend and frontend must run together.
    """

    def __init__(
        self,
        name: str,
        config: Dict[str, Any],
        children: List[Environment],
    ) -> None:
        super().__init__(name, config)
        self.children = children
        self.test_command = config.get("test_command", "")
        self._setup_envs: List[Environment] = []

    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.COMPOSITE

    def setup(self) -> SetupResult:
        """Set up all child environments in order."""
        total_start = time.time()
        details: Dict[str, Any] = {"children": {}}

        for child in self.children:
            result = child.setup()
            details["children"][child.name] = {
                "success": result.success,
                "message": result.message,
                "duration": result.duration,
            }

            if not result.success:
                # Teardown already-started environments
                for env in reversed(self._setup_envs):
                    env.teardown()
                return SetupResult(
                    success=False,
                    message=f"Child environment '{child.name}' failed: {result.message}",
                    duration=time.time() - total_start,
                    details=details,
                )

            self._setup_envs.append(child)

        # Aggregate timings
        self.timings.build = sum(c.timings.build for c in self.children)
        self.timings.startup = sum(c.timings.startup for c in self.children)

        return SetupResult(
            success=True,
            message=f"Started {len(self.children)} environments",
            duration=time.time() - total_start,
            details=details,
        )

    def is_ready(self) -> bool:
        """Check if all child environments are ready."""
        return all(child.is_ready() for child in self._setup_envs)

    def wait_ready(self, timeout: int = 120) -> bool:
        """Wait for all child environments to be ready."""
        start = time.time()
        remaining = timeout

        for child in self._setup_envs:
            if remaining <= 0:
                return False

            child_start = time.time()
            if not child.wait_ready(timeout=int(remaining)):
                return False
            remaining -= (time.time() - child_start)

        self.timings.health_check = time.time() - start
        return True

    def run_tests(
        self,
        suite: Optional[str] = None,
        category: Optional[str] = None,
        verbose: bool = False,
    ) -> TestResult:
        """
        Run tests against the composite environment.

        By default, runs tests from the last child (e.g., E2E tests).
        Can also run a custom test_command if configured.
        """
        start = time.time()

        if self.test_command:
            # Run custom composite test command
            import shlex
            import subprocess

            cmd = shlex.split(self.test_command)
            if suite:
                cmd.extend(["--suite", suite])
            if verbose:
                cmd.append("-v")

            result = subprocess.run(cmd, capture_output=True, text=True)
            self.timings.tests = time.time() - start

            return TestResult(
                passed=1 if result.returncode == 0 else 0,
                failed=0 if result.returncode == 0 else 1,
                errors=0,
                skipped=0,
                duration=self.timings.tests,
                exit_code=result.returncode,
            )

        # Default: run tests from the last child environment
        if self._setup_envs:
            result = self._setup_envs[-1].run_tests(suite, category, verbose)
            self.timings.tests = time.time() - start
            return result

        return TestResult(
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            duration=0.0,
            exit_code=2,
        )

    def teardown(self, keep_running: bool = False) -> None:
        """Tear down all child environments in reverse order."""
        start = time.time()

        for child in reversed(self._setup_envs):
            child.teardown(keep_running=keep_running)

        self._setup_envs.clear()
        self.timings.cleanup = time.time() - start


def aggregate_results(results: List[TestResult]) -> TestResult:
    """
    Aggregate multiple test results into a single result.

    Args:
        results: List of TestResult from multiple environments

    Returns:
        Combined TestResult
    """
    if not results:
        return TestResult(
            passed=0,
            failed=0,
            errors=0,
            skipped=0,
            duration=0.0,
            exit_code=0,
        )

    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_errors = sum(r.errors for r in results)
    total_skipped = sum(r.skipped for r in results)
    total_duration = sum(r.duration for r in results)

    # Exit code is worst case: 2 > 1 > 0
    exit_code = max(r.exit_code for r in results)

    return TestResult(
        passed=total_passed,
        failed=total_failed,
        errors=total_errors,
        skipped=total_skipped,
        duration=total_duration,
        exit_code=exit_code,
    )
