"""
Docker Compose environment for multi-container testing.

Uses DockerResourceManager for container lifecycle management.
Supports flexible test execution including custom scripts.
"""
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from systemeval.types import TestResult
from systemeval.environments.base import Environment, EnvironmentType, SetupResult
from systemeval.environments.executor import DockerExecutor
from systemeval.plugins.docker_manager import (
    DockerResourceManager,
    HealthCheckConfig,
)
from systemeval.utils.commands import build_test_command
from systemeval.utils.logging import get_logger

logger = get_logger(__name__)


class DockerComposeEnvironment(Environment):
    """
    Environment for Docker Compose-based testing.

    Builds images, starts containers, waits for health, runs tests inside containers.
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name, config)

        # Extract config
        self.compose_file = config.get("compose_file", "docker-compose.yml")
        self.services = config.get("services", [])
        self.test_service = config.get("test_service", "django")
        self.test_command = config.get("test_command", "pytest")
        self.working_dir = Path(config.get("working_dir", "."))
        self.skip_build = config.get("skip_build", False)
        self.project_name = config.get("project_name")

        # Health check config
        health_config = config.get("health_check", {})
        self.health_config = HealthCheckConfig(
            service=health_config.get("service", self.test_service),
            endpoint=health_config.get("endpoint", "/api/v1/health/"),
            port=health_config.get("port", 8000),
            timeout=health_config.get("timeout", 120),
        )

        # Initialize Docker manager
        self.docker = DockerResourceManager(
            compose_file=self.compose_file,
            project_dir=str(self.working_dir),
            project_name=self.project_name,
        )

        self._is_up = False

    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.DOCKER_COMPOSE

    def setup(self) -> SetupResult:
        """Build and start Docker containers."""
        logger.debug(f"Setting up Docker Compose environment: {self.name}")
        total_start = time.time()
        details: Dict[str, Any] = {}

        # Install signal handlers for clean shutdown
        self.docker.install_signal_handlers(self._cleanup)

        # Build phase
        if not self.skip_build:
            logger.debug("Building Docker images...")
            build_start = time.time()
            build_result = self.docker.build(
                services=self.services if self.services else None,
                stream=True,
            )
            self.timings.build = time.time() - build_start
            details["build"] = {
                "success": build_result.success,
                "duration": build_result.duration,
            }

            if not build_result.success:
                logger.error(f"Docker build failed: {build_result.error}")
                return SetupResult(
                    success=False,
                    message=f"Build failed: {build_result.error}",
                    duration=time.time() - total_start,
                    details=details,
                )

        # Start containers
        logger.debug(f"Starting Docker containers (services: {self.services or 'all'})...")
        startup_start = time.time()
        up_result = self.docker.up(
            services=self.services if self.services else None,
            detach=True,
            build=False,  # Already built
        )
        self.timings.startup = time.time() - startup_start
        details["startup"] = {
            "success": up_result.success,
            "duration": up_result.duration,
        }

        if not up_result.success:
            logger.error(f"Failed to start containers: {up_result.stderr}")
            return SetupResult(
                success=False,
                message=f"Failed to start containers: {up_result.stderr}",
                duration=time.time() - total_start,
                details=details,
            )

        self._is_up = True
        logger.debug(f"Docker containers started successfully in {time.time() - total_start:.1f}s")

        return SetupResult(
            success=True,
            message=f"Started {len(self.services) or 'all'} services",
            duration=time.time() - total_start,
            details=details,
        )

    def is_ready(self) -> bool:
        """Check if containers are healthy."""
        if not self._is_up:
            return False
        return self.docker.is_healthy(self.health_config.service)

    def wait_ready(self, timeout: int = 120) -> bool:
        """Wait for health check endpoint."""
        if not self._is_up:
            return False

        start = time.time()
        config = HealthCheckConfig(
            service=self.health_config.service,
            endpoint=self.health_config.endpoint,
            port=self.health_config.port,
            timeout=timeout,
        )

        def on_progress(msg: str) -> None:
            print(f"  {msg}")

        result = self.docker.wait_healthy(config, on_progress=on_progress)
        self.timings.health_check = time.time() - start

        return result

    def run_tests(
        self,
        suite: Optional[str] = None,
        category: Optional[str] = None,
        verbose: bool = False,
    ) -> TestResult:
        """
        Run tests inside the test service container.

        Supports:
        - Simple commands: "pytest -v"
        - Shell scripts: "./scripts/run-e2e.sh"
        - Multi-step: ["npm run build", "npm test"]
        - Complex pipelines: "cd app && ./run-tests.sh"
        """
        if not self._is_up:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                exit_code=2,
            )

        start = time.time()

        # Create Docker executor
        executor = DockerExecutor(
            container=self.test_service,
            compose_file=self.compose_file,
            project_dir=str(self.working_dir),
            project_name=self.project_name,
            verbose=verbose,
        )

        # Build test command with optional filters
        command = self._build_test_command(suite, category, verbose)

        # Execute tests
        result = executor.execute(
            command=command,
            timeout=self.config.get("test_timeout"),
            env=self.config.get("test_env", {}),
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

    def _cleanup(self) -> None:
        """Internal cleanup for signal handlers."""
        if self._is_up:
            self.docker.down()
            self._is_up = False

    def teardown(self, keep_running: bool = False) -> None:
        """Stop and remove containers."""
        logger.debug(f"Tearing down Docker Compose environment (keep_running={keep_running})")
        start = time.time()

        if self._is_up and not keep_running:
            self.docker.down()
            self._is_up = False
            logger.debug(f"Docker containers stopped in {time.time() - start:.1f}s")

        self.docker.restore_signal_handlers()
        self.timings.cleanup = time.time() - start
