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
        """
        Build Docker images from compose file.

        Args:
            services: Specific services to build (None = all)
            no_cache: Build without cache
            pull: Pull base images before building
            stream: Stream build output
        """
        args = ["build"]
        if no_cache:
            args.append("--no-cache")
        if pull:
            args.append("--pull")
        if services:
            args.extend(services)

        result = self._run(*args, stream=stream)

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
        """
        Start containers.

        Args:
            services: Specific services to start (None = all)
            detach: Run in background
            build: Build images before starting
            wait: Wait for services to be healthy (Docker native)
            timeout: Timeout for wait
        """
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

        return self._run(*args, stream=not detach)

    def down(
        self,
        volumes: bool = False,
        remove_orphans: bool = True,
        timeout: int = 10,
    ) -> CommandResult:
        """
        Stop and remove containers.

        Args:
            volumes: Also remove volumes (DANGEROUS - data loss!)
            remove_orphans: Remove orphaned containers
            timeout: Timeout for container stop
        """
        args = ["down", "-t", str(timeout)]
        if volumes:
            args.append("-v")
        if remove_orphans:
            args.append("--remove-orphans")

        return self._run(*args)

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
        """
        Execute a command inside a running container.

        Args:
            service: Service name to exec into
            command: Command and arguments
            workdir: Working directory inside container
            user: User to run as
            env: Environment variables
            timeout: Command timeout
            stream: Stream output in real-time
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
        """
        Get container logs.

        Args:
            service: Specific service (None = all)
            tail: Number of lines to show
            follow: Follow log output
            timestamps: Show timestamps
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
        """List containers and their status."""
        args = ["ps", "--format", "json"]
        if services:
            args.extend(services)
        return self._run(*args)

    def is_running(self, service: str) -> bool:
        """Check if a service container is running."""
        result = self._run("ps", "-q", service)
        return result.success and bool(result.stdout.strip())

    def is_healthy(self, service: str) -> bool:
        """Check if a service is healthy (via docker inspect)."""
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
        except Exception:
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
        start = time.time()
        interval = config.initial_delay
        attempts = 0

        # Build health URL - use localhost since we're checking from host
        url = f"http://localhost:{config.port}{config.endpoint}"

        while (time.time() - start) < config.timeout:
            if self._shutdown_requested:
                return False

            attempts += 1
            try:
                response = urlopen(url, timeout=5)
                if response.status == 200:
                    if on_progress:
                        on_progress(f"Service {config.service} is healthy")
                    return True
            except URLError:
                pass
            except Exception as e:
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
        """Restore original signal handlers."""
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm:
            signal.signal(signal.SIGTERM, self._original_sigterm)
        self._shutdown_requested = False
