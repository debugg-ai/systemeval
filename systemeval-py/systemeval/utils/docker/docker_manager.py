"""
Docker Resource Manager for orchestrating Docker Compose environments.

Provides build, up, down, exec, logs, and health check functionality.
"""
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

from systemeval.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CommandResult:
    """Result of a Docker command execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class BuildResult:
    """Result of building Docker images."""
    success: bool
    services_built: List[str] = field(default_factory=list)
    duration: float = 0.0
    output: str = ""
    error: str = ""


@dataclass
class HealthCheckConfig:
    """Configuration for health check polling."""
    service: str
    endpoint: str = "/health/"
    port: int = 8000
    timeout: int = 120
    initial_delay: float = 2.0
    max_interval: float = 10.0


class DockerResourceManager:
    """
    Manages Docker Compose resources for test environments.

    Uses subprocess to call docker compose (v2) directly for maximum
    compatibility and debuggability.
    """

    def __init__(
        self,
        compose_file: str = "docker-compose.yml",
        project_dir: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> None:
        """
        Initialize the Docker resource manager.

        Args:
            compose_file: Path to docker-compose.yml file
            project_dir: Directory containing compose file (defaults to cwd)
            project_name: Override project name (defaults to directory name)
        """
        self.compose_file = compose_file
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.project_name = project_name
        self._shutdown_requested = False
        self._original_sigint = None
        self._original_sigterm = None

    def _compose_cmd(self, *args: str) -> List[str]:
        """Build docker compose command with common options."""
        cmd = ["docker", "compose", "-f", self.compose_file]
        if self.project_name:
            cmd.extend(["-p", self.project_name])
        cmd.extend(args)
        return cmd

    def _run(
        self,
        *args: str,
        capture: bool = True,
        stream: bool = False,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """
        Run a docker compose command.

        Args:
            args: Command arguments
            capture: Capture stdout/stderr
            stream: Stream output in real-time
            timeout: Command timeout in seconds
        """
        cmd = self._compose_cmd(*args)
        start = time.time()

        try:
            if stream:
                # Stream output in real-time
                process = subprocess.Popen(
                    cmd,
                    cwd=self.project_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                output_lines = []
                for line in iter(process.stdout.readline, ""):
                    print(line, end="")
                    output_lines.append(line)
                process.wait(timeout=timeout)
                return CommandResult(
                    exit_code=process.returncode,
                    stdout="".join(output_lines),
                    stderr="",
                    duration=time.time() - start,
                )
            else:
                result = subprocess.run(
                    cmd,
                    cwd=self.project_dir,
                    capture_output=capture,
                    text=True,
                    timeout=timeout,
                )
                return CommandResult(
                    exit_code=result.returncode,
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    duration=time.time() - start,
                )
        except subprocess.TimeoutExpired:
            return CommandResult(
                exit_code=124,  # Standard timeout exit code
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration=time.time() - start,
            )
        except Exception as e:
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration=time.time() - start,
            )

    def build(
        self,
        services: Optional[List[str]] = None,
        no_cache: bool = False,
        pull: bool = True,
        stream: bool = True,
    ) -> BuildResult:
        """Build Docker images from the compose file.

        Executes `docker compose build` with the specified options. Images are
        built according to the Dockerfile specifications in the compose file.

        Args:
            services: Specific services to build. If None, builds all services
                      defined in the compose file.
            no_cache: Build without using Docker layer cache. Useful for
                      debugging build issues or ensuring fresh builds.
            pull: Pull base images before building to ensure latest versions.
            stream: Stream build output to stdout in real-time. If False,
                    output is captured and returned in BuildResult.

        Returns:
            BuildResult containing:
            - success: True if all images built successfully
            - services_built: List of service names that were built
            - duration: Build time in seconds
            - output: Build output (if not streaming)
            - error: Error message if build failed
        """
        logger.debug(f"Building Docker images (services: {services or 'all'}, no_cache: {no_cache})")
        args = ["build"]
        if no_cache:
            args.append("--no-cache")
        if pull:
            args.append("--pull")
        if services:
            args.extend(services)

        result = self._run(*args, stream=stream)

        if result.success:
            logger.debug(f"Docker build completed successfully in {result.duration:.1f}s")
        else:
            logger.error(f"Docker build failed: {result.stderr[:200]}")

        return BuildResult(
            success=result.success,
            services_built=services or [],
            duration=result.duration,
            output=result.stdout,
            error=result.stderr,
        )

    def up(
        self,
        services: Optional[List[str]] = None,
        detach: bool = True,
        build: bool = False,
        wait: bool = False,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """Start containers from the compose file.

        Executes `docker compose up` to create and start containers for the
        specified services. Containers are started according to the compose
        file's dependency order.

        Args:
            services: Specific services to start. If None, starts all services
                      defined in the compose file.
            detach: Run containers in background (daemon mode). If False,
                    attaches to containers and streams output.
            build: Build images before starting containers. Equivalent to
                   running `docker compose build` first.
            wait: Wait for services to become healthy before returning.
                  Requires health checks defined in the compose file.
            timeout: Timeout in seconds for the wait flag.

        Returns:
            CommandResult with exit_code, stdout, stderr, and duration.
            exit_code 0 indicates all containers started successfully.
        """
        logger.debug(f"Starting Docker containers (services: {services or 'all'}, detach: {detach})")
        args = ["up"]
        if detach:
            args.append("-d")
        if build:
            args.append("--build")
        if wait:
            args.append("--wait")
            if timeout:
                args.extend(["--wait-timeout", str(timeout)])
        if services:
            args.extend(services)

        result = self._run(*args, stream=not detach)

        if result.success:
            logger.debug(f"Docker containers started successfully in {result.duration:.1f}s")
        else:
            logger.error(f"Failed to start Docker containers: {result.stderr[:200]}")

        return result

    def down(
        self,
        volumes: bool = False,
        remove_orphans: bool = True,
        timeout: int = 10,
    ) -> CommandResult:
        """Stop and remove containers, networks, and optionally volumes.

        Executes `docker compose down` to gracefully stop containers and remove
        them along with their networks. This is the proper cleanup method.

        Args:
            volumes: Also remove named volumes declared in the compose file.
                     WARNING: This causes permanent data loss! Database contents,
                     uploaded files, and other persistent data will be deleted.
            remove_orphans: Remove containers for services not defined in the
                           current compose file (leftover from previous runs).
            timeout: Seconds to wait for containers to stop gracefully before
                     force-killing them.

        Returns:
            CommandResult with exit_code, stdout, stderr, and duration.
            exit_code 0 indicates cleanup completed successfully.

        Warning:
            The volumes=True flag permanently deletes all data stored in Docker
            volumes. Use with extreme caution, especially in production.
        """
        if volumes:
            logger.warning("Stopping Docker containers WITH volume removal - data will be lost!")
        else:
            logger.debug(f"Stopping Docker containers (timeout: {timeout}s)")

        args = ["down", "-t", str(timeout)]
        if volumes:
            args.append("-v")
        if remove_orphans:
            args.append("--remove-orphans")

        result = self._run(*args)

        if result.success:
            logger.debug(f"Docker containers stopped successfully in {result.duration:.1f}s")
        else:
            logger.error(f"Failed to stop Docker containers: {result.stderr[:200]}")

        return result

    def exec(
        self,
        service: str,
        command: List[str],
        workdir: Optional[str] = None,
        user: Optional[str] = None,
        env: Optional[dict] = None,
        timeout: Optional[int] = None,
        stream: bool = False,
    ) -> CommandResult:
        """Execute a command inside a running container.

        Executes `docker compose exec` to run a command in an existing container.
        The container must be running. Uses -T to disable pseudo-TTY for
        non-interactive execution.

        Args:
            service: Name of the service/container to execute in.
            command: Command and arguments as a list (e.g., ['pytest', '-v']).
            workdir: Working directory inside the container. Overrides the
                     container's default working directory.
            user: Run command as this user (e.g., 'root', 'www-data').
            env: Additional environment variables to set for the command.
            timeout: Maximum execution time in seconds. Process is killed
                     after timeout (exit code 124).
            stream: Stream output to stdout in real-time.

        Returns:
            CommandResult with the command's exit_code, stdout, stderr,
            and duration. exit_code matches the executed command's exit code.

        Example:
            result = manager.exec('backend', ['pytest', '-v', 'tests/'])
            if result.success:
                print(f"Tests passed in {result.duration}s")
        """
        args = ["exec", "-T"]  # -T disables pseudo-TTY
        if workdir:
            args.extend(["-w", workdir])
        if user:
            args.extend(["-u", user])
        if env:
            for key, value in env.items():
                args.extend(["-e", f"{key}={value}"])

        args.append(service)
        args.extend(command)

        return self._run(*args, timeout=timeout, stream=stream)

    def logs(
        self,
        service: Optional[str] = None,
        tail: int = 100,
        follow: bool = False,
        timestamps: bool = False,
    ) -> CommandResult:
        """Retrieve container logs.

        Executes `docker compose logs` to fetch logs from containers.
        Useful for debugging startup issues or viewing test output.

        Args:
            service: Specific service to get logs from. If None, returns
                     logs from all services (interleaved).
            tail: Number of log lines to retrieve from the end. Set to 0
                  for all available logs.
            follow: Follow log output in real-time (like `tail -f`).
                    Blocks until interrupted.
            timestamps: Include timestamps with each log line.

        Returns:
            CommandResult with logs in stdout. If follow=True, streams
            output and returns when interrupted.
        """
        args = ["logs", "--tail", str(tail)]
        if follow:
            args.append("-f")
        if timestamps:
            args.append("-t")
        if service:
            args.append(service)

        return self._run(*args, stream=follow)

    def ps(self, services: Optional[List[str]] = None) -> CommandResult:
        """List containers and their current status.

        Executes `docker compose ps` to show container states. Output is
        JSON-formatted for easy parsing.

        Args:
            services: Specific services to list. If None, lists all.

        Returns:
            CommandResult with JSON output in stdout containing container
            names, states, ports, and health status.
        """
        args = ["ps", "--format", "json"]
        if services:
            args.extend(services)
        return self._run(*args)

    def is_running(self, service: str) -> bool:
        """Check if a service container is currently running.

        Args:
            service: Name of the service to check.

        Returns:
            True if the container exists and is running, False otherwise.
        """
        result = self._run("ps", "-q", service)
        return result.success and bool(result.stdout.strip())

    def is_healthy(self, service: str) -> bool:
        """Check if a service container is healthy via Docker health check.

        Uses `docker inspect` to query the container's health status. Requires
        the service to have a HEALTHCHECK defined in its Dockerfile or compose.

        Args:
            service: Name of the service to check.

        Returns:
            True if the container's health status is "healthy", False otherwise
            (including if no health check is defined or container isn't running).
        """
        cmd = [
            "docker", "inspect", "--format",
            "{{.State.Health.Status}}",
            f"{self.project_name or self.project_dir.name}-{service}-1"
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_dir,
            )
            return result.stdout.strip() == "healthy"
        except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
            logger.debug(f"Docker health check failed: {e}")
            return False

    def wait_healthy(
        self,
        config: HealthCheckConfig,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Wait for a service to be healthy via HTTP endpoint.

        Args:
            config: Health check configuration
            on_progress: Callback for progress updates

        Returns:
            True if healthy within timeout, False otherwise
        """
        logger.debug(f"Waiting for service '{config.service}' to be healthy at {config.endpoint}")
        start = time.time()
        interval = config.initial_delay
        attempts = 0

        # Build health URL - use localhost since we're checking from host
        url = f"http://localhost:{config.port}{config.endpoint}"

        while (time.time() - start) < config.timeout:
            if self._shutdown_requested:
                logger.warning("Health check cancelled due to shutdown request")
                return False

            attempts += 1
            try:
                response = urlopen(url, timeout=5)
                if response.status == 200:
                    logger.debug(f"Service '{config.service}' is healthy after {attempts} attempts ({time.time() - start:.1f}s)")
                    if on_progress:
                        on_progress(f"Service {config.service} is healthy")
                    return True
            except URLError:
                pass
            except Exception as e:
                logger.debug(f"Health check error (attempt {attempts}): {e}")
                if on_progress:
                    on_progress(f"Health check error: {e}")

            elapsed = time.time() - start
            if on_progress:
                on_progress(
                    f"Waiting for {config.service}... "
                    f"({attempts} attempts, {elapsed:.0f}s elapsed)"
                )

            time.sleep(interval)
            interval = min(interval * 1.5, config.max_interval)

        logger.warning(f"Service '{config.service}' did not become healthy within {config.timeout}s timeout")
        return False

    def install_signal_handlers(self, cleanup_callback: Callable[[], None]) -> None:
        """
        Install signal handlers for clean shutdown.

        Args:
            cleanup_callback: Function to call on shutdown signal
        """
        def handler(signum, frame):
            self._shutdown_requested = True
            cleanup_callback()
            # Re-raise to allow normal termination
            if signum == signal.SIGINT:
                raise KeyboardInterrupt
            elif signum == signal.SIGTERM:
                raise SystemExit(128 + signum)

        self._original_sigint = signal.signal(signal.SIGINT, handler)
        self._original_sigterm = signal.signal(signal.SIGTERM, handler)

    def restore_signal_handlers(self) -> None:
        """Restore original signal handlers after test execution.

        Should be called after test execution completes to restore the
        signal handlers that were replaced by install_signal_handlers().
        Also clears the shutdown_requested flag.
        """
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm:
            signal.signal(signal.SIGTERM, self._original_sigterm)
        self._shutdown_requested = False
