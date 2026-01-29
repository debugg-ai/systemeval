"""
E2E Docker proof test: systemeval orchestrates build, start, test, teardown
for all 3 example projects using DockerComposeEnvironment.

These tests actually build Docker images, start containers, run tests
inside them, and tear down — proving the full systemeval Docker lifecycle.

Requires: Docker daemon running.
Run with: pytest tests/test_e2e_docker_projects.py -v --timeout=600
"""
import os
import pytest
from pathlib import Path

from systemeval.environments.implementations.docker_compose import DockerComposeEnvironment


# Absolute path to example projects
EXAMPLES_DIR = Path(__file__).parent.parent / "example-usage-projects"


def _is_docker_available() -> bool:
    """Check if Docker is available for E2E tests."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


skip_no_docker = pytest.mark.skipif(
    not _is_docker_available(),
    reason="Docker daemon not available",
)


# ---------------------------------------------------------------------------
# Project 1: django-rest-api (docker-compose.yml, postgres, redis, pytest)
# ---------------------------------------------------------------------------
@skip_no_docker
class TestDjangoRestApiE2E:
    """Full lifecycle: build → start → pytest in container → teardown."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        project_dir = str(EXAMPLES_DIR / "django-rest-api")
        self.env = DockerComposeEnvironment(
            name="django-e2e",
            config={
                "compose_file": "docker-compose.yml",
                "working_dir": project_dir,
                "test_service": "django",
                "test_command": "pytest",
                "auto_discover": False,
                "health_check": {
                    "endpoint": "/api/health/",
                    "port": 8000,
                    "timeout": 120,
                },
            },
        )
        yield
        self.env.teardown()

    def test_setup_builds_and_starts(self):
        result = self.env.setup()
        assert result.success, f"Setup failed: {result.message}"
        assert self.env._is_up

    def test_containers_come_up(self):
        result = self.env.setup()
        assert result.success
        # Verify test service is running
        assert self.env.docker.is_running("django")

    def test_exec_pytest_in_container(self):
        result = self.env.setup()
        assert result.success

        exec_result = self.env.docker.exec(
            service="django",
            command=["pytest", "--tb=short", "-q"],
            timeout=60,
        )
        assert exec_result.success, f"Tests failed:\n{exec_result.stdout}\n{exec_result.stderr}"
        assert "passed" in exec_result.stdout

    def test_dependent_services_running(self):
        result = self.env.setup()
        assert result.success
        assert self.env.docker.is_running("postgres")
        assert self.env.docker.is_running("redis")


# ---------------------------------------------------------------------------
# Project 2: express-mongo-api (compose.yml, mongo, jest)
# ---------------------------------------------------------------------------
@skip_no_docker
class TestExpressMongoApiE2E:
    """Full lifecycle: build → start → jest in container → teardown."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        project_dir = str(EXAMPLES_DIR / "express-mongo-api")
        self.env = DockerComposeEnvironment(
            name="express-e2e",
            config={
                "compose_file": "compose.yml",
                "working_dir": project_dir,
                "test_service": "api",
                "test_command": "npm test",
                "auto_discover": False,
                "health_check": {
                    "endpoint": "/health",
                    "port": 3000,
                    "timeout": 120,
                },
            },
        )
        yield
        self.env.teardown()

    def test_setup_builds_and_starts(self):
        result = self.env.setup()
        assert result.success, f"Setup failed: {result.message}"

    def test_exec_jest_in_container(self):
        result = self.env.setup()
        assert result.success

        exec_result = self.env.docker.exec(
            service="api",
            command=["npm", "test"],
            timeout=120,
        )
        assert exec_result.success, f"Tests failed:\n{exec_result.stdout}\n{exec_result.stderr}"
        assert "passed" in exec_result.stdout.lower() or "Tests:" in exec_result.stdout

    def test_mongo_service_running(self):
        result = self.env.setup()
        assert result.success
        assert self.env.docker.is_running("mongo")


# ---------------------------------------------------------------------------
# Project 3: fastapi-react-fullstack (local.yml, multi-service, pytest+jest)
# ---------------------------------------------------------------------------
@skip_no_docker
class TestFastApiReactFullstackE2E:
    """Full lifecycle: build → start → pytest backend + jest frontend → teardown."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        project_dir = str(EXAMPLES_DIR / "fastapi-react-fullstack")
        self.env = DockerComposeEnvironment(
            name="fullstack-e2e",
            config={
                "compose_file": "local.yml",
                "working_dir": project_dir,
                "test_service": "backend",
                "test_command": "pytest",
                "auto_discover": False,
                "health_check": {
                    "endpoint": "/health",
                    "port": 8080,
                    "timeout": 120,
                },
            },
        )
        yield
        self.env.teardown()

    def test_setup_builds_and_starts(self):
        result = self.env.setup()
        assert result.success, f"Setup failed: {result.message}"

    def test_exec_pytest_in_backend(self):
        result = self.env.setup()
        assert result.success

        exec_result = self.env.docker.exec(
            service="backend",
            command=["pytest", "--tb=short", "-q"],
            timeout=60,
        )
        assert exec_result.success, f"Backend tests failed:\n{exec_result.stdout}\n{exec_result.stderr}"
        assert "passed" in exec_result.stdout

    def test_exec_jest_in_frontend(self):
        result = self.env.setup()
        assert result.success

        exec_result = self.env.docker.exec(
            service="frontend",
            command=["npm", "test"],
            timeout=120,
        )
        assert exec_result.success, f"Frontend tests failed:\n{exec_result.stdout}\n{exec_result.stderr}"
        assert "passed" in exec_result.stdout.lower() or "Tests:" in exec_result.stdout

    def test_all_services_running(self):
        result = self.env.setup()
        assert result.success
        assert self.env.docker.is_running("backend")
        assert self.env.docker.is_running("frontend")
        assert self.env.docker.is_running("postgres")
        assert self.env.docker.is_running("nginx")


# ---------------------------------------------------------------------------
# Cross-project orchestration: all 3 projects in sequence
# ---------------------------------------------------------------------------
@skip_no_docker
class TestCrossProjectOrchestration:
    """Prove systemeval can orchestrate multiple distinct Docker projects."""

    def test_all_three_projects_build_run_test_teardown(self):
        """The definitive E2E test: all 3 projects lifecycle via systemeval."""
        projects = [
            {
                "name": "django-rest-api",
                "config": {
                    "compose_file": "docker-compose.yml",
                    "working_dir": str(EXAMPLES_DIR / "django-rest-api"),
                    "test_service": "django",
                    "auto_discover": False,
                    "health_check": {"endpoint": "/api/health/", "port": 8000},
                },
                "test_cmd": ["pytest", "--tb=short", "-q"],
            },
            {
                "name": "express-mongo-api",
                "config": {
                    "compose_file": "compose.yml",
                    "working_dir": str(EXAMPLES_DIR / "express-mongo-api"),
                    "test_service": "api",
                    "auto_discover": False,
                    "health_check": {"endpoint": "/health", "port": 3000},
                },
                "test_cmd": ["npm", "test"],
            },
            {
                "name": "fastapi-react-fullstack",
                "config": {
                    "compose_file": "local.yml",
                    "working_dir": str(EXAMPLES_DIR / "fastapi-react-fullstack"),
                    "test_service": "backend",
                    "auto_discover": False,
                    "health_check": {"endpoint": "/health", "port": 8080},
                },
                "test_cmd": ["pytest", "--tb=short", "-q"],
            },
        ]

        results = {}

        for project in projects:
            env = DockerComposeEnvironment(
                name=project["name"],
                config=project["config"],
            )
            try:
                # Build + start
                setup_result = env.setup()
                assert setup_result.success, (
                    f"{project['name']} setup failed: {setup_result.message}"
                )

                # Execute tests inside container
                exec_result = env.docker.exec(
                    service=project["config"]["test_service"],
                    command=project["test_cmd"],
                    timeout=120,
                )
                assert exec_result.success, (
                    f"{project['name']} tests failed (exit {exec_result.exit_code}):\n"
                    f"{exec_result.stdout}\n{exec_result.stderr}"
                )

                results[project["name"]] = {
                    "setup": True,
                    "tests": True,
                    "exit_code": exec_result.exit_code,
                }
            finally:
                env.teardown()

        # All 3 projects passed
        assert len(results) == 3
        for name, r in results.items():
            assert r["setup"], f"{name} setup failed"
            assert r["tests"], f"{name} tests failed"
            assert r["exit_code"] == 0, f"{name} exit code: {r['exit_code']}"
