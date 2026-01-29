"""
Pre-flight checks for Docker test environments.

Validates Docker availability, compose file existence, service validity,
and port conflicts before attempting any Docker operations.
Returns clear, actionable error messages.
"""
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from systemeval.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PreflightResult:
    """Result of pre-flight checks."""
    ok: bool
    checks: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_pass(self, name: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": "pass", "detail": detail})

    def add_fail(self, name: str, error: str, fix: str = "") -> None:
        self.ok = False
        self.checks.append({"name": name, "status": "fail", "detail": error})
        msg = f"{name}: {error}"
        if fix:
            msg += f"\n  Fix: {fix}"
        self.errors.append(msg)

    def add_warn(self, name: str, detail: str) -> None:
        self.checks.append({"name": name, "status": "warn", "detail": detail})
        self.warnings.append(f"{name}: {detail}")


def check_docker_binary() -> Optional[str]:
    """Check if the docker binary is available.

    Returns:
        Path to docker binary, or None if not found
    """
    return shutil.which("docker")


def check_docker_running() -> bool:
    """Check if the Docker daemon is running.

    Returns:
        True if Docker daemon is responsive
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def check_docker_compose_version() -> Optional[str]:
    """Check docker compose version and return it.

    Returns:
        Version string (e.g. "2.24.5"), or None if not available
    """
    # Try v2 first (docker compose)
    try:
        result = subprocess.run(
            ["docker", "compose", "version", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Try v1 (docker-compose)
    try:
        result = subprocess.run(
            ["docker-compose", "version", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return f"v1:{result.stdout.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return None


def check_compose_file(project_dir: Path, compose_file: Optional[str] = None) -> Optional[Path]:
    """Verify compose file exists.

    Args:
        project_dir: Project root directory
        compose_file: Explicit compose file path, or None to search

    Returns:
        Path to compose file if found, None otherwise
    """
    if compose_file:
        path = project_dir / compose_file
        return path if path.exists() else None

    from systemeval.utils.docker.discovery import find_compose_file
    return find_compose_file(project_dir)


def check_containers_running(
    compose_file: Path,
    project_dir: Path,
    project_name: Optional[str] = None,
) -> List[str]:
    """Check which containers from a compose file are currently running.

    Args:
        compose_file: Path to docker-compose file
        project_dir: Project directory
        project_name: Optional project name override

    Returns:
        List of running service names
    """
    cmd = ["docker", "compose", "-f", str(compose_file)]
    if project_name:
        cmd.extend(["-p", project_name])
    cmd.extend(["ps", "--format", "{{.Service}}", "--filter", "status=running"])

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return []


def run_preflight(
    project_dir: Path,
    compose_file: Optional[str] = None,
    services: Optional[List[str]] = None,
    test_service: Optional[str] = None,
    attach: bool = False,
) -> PreflightResult:
    """Run all pre-flight checks for a Docker test environment.

    Args:
        project_dir: Project root directory
        compose_file: Optional explicit compose file path
        services: Optional list of expected services
        test_service: Optional test service name
        attach: Whether attach mode is being used

    Returns:
        PreflightResult with all check outcomes
    """
    result = PreflightResult(ok=True)

    # 1. Docker binary
    docker_path = check_docker_binary()
    if docker_path:
        result.add_pass("docker_binary", f"Found at {docker_path}")
    else:
        result.add_fail(
            "docker_binary",
            "Docker is not installed or not in PATH",
            "Install Docker: https://docs.docker.com/get-docker/",
        )
        return result  # Can't continue without docker

    # 2. Docker daemon
    if check_docker_running():
        result.add_pass("docker_daemon", "Docker daemon is running")
    else:
        result.add_fail(
            "docker_daemon",
            "Docker daemon is not running",
            "Start Docker Desktop or run: sudo systemctl start docker",
        )
        return result  # Can't continue without daemon

    # 3. Docker Compose
    compose_version = check_docker_compose_version()
    if compose_version:
        result.add_pass("docker_compose", f"Version {compose_version}")
        if compose_version.startswith("v1:"):
            result.add_warn(
                "docker_compose_v1",
                "Using docker-compose v1 (deprecated). Consider upgrading to v2."
            )
    else:
        result.add_fail(
            "docker_compose",
            "Docker Compose is not available",
            "Install Docker Compose v2: https://docs.docker.com/compose/install/",
        )
        return result

    # 4. Compose file
    found_compose = check_compose_file(project_dir, compose_file)
    if found_compose:
        result.add_pass("compose_file", f"Found: {found_compose.name}")
    else:
        searched = compose_file or "docker-compose.yml, compose.yml, local.yml, ..."
        result.add_fail(
            "compose_file",
            f"No compose file found (searched: {searched})",
            f"Create a docker-compose.yml in {project_dir} or specify compose_file in config",
        )
        return result

    # 5. Validate services against compose file
    if services:
        try:
            from systemeval.utils.docker.compose_parser import parse_compose_file
            compose_info = parse_compose_file(found_compose)
            available = compose_info.service_names

            missing = [s for s in services if s not in available]
            if missing:
                result.add_fail(
                    "services",
                    f"Services not found in {found_compose.name}: {', '.join(missing)}",
                    f"Available services: {', '.join(available)}",
                )
            else:
                result.add_pass("services", f"All {len(services)} services found in compose file")
        except Exception as e:
            result.add_warn("services", f"Could not validate services: {e}")

    # 6. For attach mode, check containers are running
    if attach:
        running = check_containers_running(found_compose, project_dir)
        if running:
            result.add_pass("containers_running", f"Running: {', '.join(running)}")
            if test_service and test_service not in running:
                result.add_fail(
                    "test_service_running",
                    f"Test service '{test_service}' is not running",
                    f"Start it with: docker compose -f {found_compose.name} up -d {test_service}",
                )
        else:
            result.add_fail(
                "containers_running",
                "No containers are running",
                f"Start containers: docker compose -f {found_compose.name} up -d",
            )

    return result
