"""Tests for DockerResourceManager - Docker Compose orchestration manager.

Covers:
- Dataclass construction and properties
- Command composition and execution
- Container lifecycle (build, up, down)
- Exec and logs operations
- Health checks (is_running, is_healthy, wait_healthy)
- Signal handler management
- Error handling paths
"""

import signal
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from systemeval.utils.docker import (
    BuildResult,
    CommandResult,
    DockerResourceManager,
    HealthCheckConfig,
)


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_command_result_success_true_when_exit_code_zero(self):
        """Test success property returns True when exit_code is 0."""
        result = CommandResult(exit_code=0, stdout="output", stderr="")
        assert result.success is True

    def test_command_result_success_false_when_exit_code_nonzero(self):
        """Test success property returns False when exit_code is non-zero."""
        result = CommandResult(exit_code=1, stdout="", stderr="error")
        assert result.success is False

    def test_command_result_success_false_with_timeout_code(self):
        """Test success property returns False with timeout exit code 124."""
        result = CommandResult(exit_code=124, stdout="", stderr="timeout")
        assert result.success is False

    def test_command_result_default_duration(self):
        """Test CommandResult has default duration of 0.0."""
        result = CommandResult(exit_code=0, stdout="", stderr="")
        assert result.duration == 0.0

    def test_command_result_with_custom_duration(self):
        """Test CommandResult accepts custom duration."""
        result = CommandResult(exit_code=0, stdout="", stderr="", duration=5.5)
        assert result.duration == 5.5

    def test_command_result_stores_stdout_stderr(self):
        """Test CommandResult stores stdout and stderr correctly."""
        result = CommandResult(
            exit_code=0,
            stdout="output line 1\noutput line 2",
            stderr="warning: something",
        )
        assert result.stdout == "output line 1\noutput line 2"
        assert result.stderr == "warning: something"


class TestBuildResult:
    """Tests for BuildResult dataclass."""

    def test_build_result_success_flag(self):
        """Test BuildResult success flag."""
        result = BuildResult(success=True)
        assert result.success is True

        result = BuildResult(success=False)
        assert result.success is False

    def test_build_result_default_values(self):
        """Test BuildResult default values."""
        result = BuildResult(success=True)
        assert result.services_built == []
        assert result.duration == 0.0
        assert result.output == ""
        assert result.error == ""

    def test_build_result_with_services(self):
        """Test BuildResult with services list."""
        result = BuildResult(
            success=True,
            services_built=["web", "db", "redis"],
            duration=45.2,
            output="Building web...\nBuilding db...",
        )
        assert result.services_built == ["web", "db", "redis"]
        assert result.duration == 45.2
        assert "Building web" in result.output

    def test_build_result_with_error(self):
        """Test BuildResult with error message."""
        result = BuildResult(
            success=False,
            error="Dockerfile not found",
        )
        assert result.success is False
        assert result.error == "Dockerfile not found"


class TestHealthCheckConfig:
    """Tests for HealthCheckConfig dataclass."""

    def test_health_check_config_required_service(self):
        """Test HealthCheckConfig requires service name."""
        config = HealthCheckConfig(service="web")
        assert config.service == "web"

    def test_health_check_config_default_values(self):
        """Test HealthCheckConfig default values."""
        config = HealthCheckConfig(service="api")
        assert config.endpoint == "/health/"
        assert config.port == 8000
        assert config.timeout == 120
        assert config.initial_delay == 2.0
        assert config.max_interval == 10.0

    def test_health_check_config_custom_values(self):
        """Test HealthCheckConfig with custom values."""
        config = HealthCheckConfig(
            service="backend",
            endpoint="/api/health",
            port=8080,
            timeout=60,
            initial_delay=1.0,
            max_interval=5.0,
        )
        assert config.service == "backend"
        assert config.endpoint == "/api/health"
        assert config.port == 8080
        assert config.timeout == 60
        assert config.initial_delay == 1.0
        assert config.max_interval == 5.0


class TestDockerResourceManagerInit:
    """Tests for DockerResourceManager initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        with patch.object(Path, "cwd", return_value=Path("/default/path")):
            manager = DockerResourceManager()
            assert manager.compose_file == "docker-compose.yml"
            assert manager.project_dir == Path("/default/path")
            assert manager.project_name is None
            assert manager._shutdown_requested is False
            assert manager._original_sigint is None
            assert manager._original_sigterm is None

    def test_init_with_custom_compose_file(self):
        """Test initialization with custom compose file."""
        manager = DockerResourceManager(
            compose_file="local.yml",
            project_dir="/test/dir",
        )
        assert manager.compose_file == "local.yml"

    def test_init_with_project_dir(self):
        """Test initialization with project directory."""
        manager = DockerResourceManager(project_dir="/my/project")
        assert manager.project_dir == Path("/my/project")

    def test_init_with_project_name(self):
        """Test initialization with project name override."""
        manager = DockerResourceManager(
            project_dir="/my/project",
            project_name="my-custom-project",
        )
        assert manager.project_name == "my-custom-project"


class TestDockerResourceManagerComposeCmd:
    """Tests for _compose_cmd method."""

    def test_compose_cmd_basic(self):
        """Test basic compose command construction."""
        manager = DockerResourceManager(
            compose_file="docker-compose.yml",
            project_dir="/test",
        )
        cmd = manager._compose_cmd("up", "-d")
        assert cmd == ["docker", "compose", "-f", "docker-compose.yml", "up", "-d"]

    def test_compose_cmd_with_project_name(self):
        """Test compose command includes project name when set."""
        manager = DockerResourceManager(
            compose_file="local.yml",
            project_dir="/test",
            project_name="myproject",
        )
        cmd = manager._compose_cmd("up")
        assert cmd == [
            "docker", "compose", "-f", "local.yml",
            "-p", "myproject", "up"
        ]

    def test_compose_cmd_multiple_args(self):
        """Test compose command with multiple arguments."""
        manager = DockerResourceManager(
            compose_file="test.yml",
            project_dir="/test",
        )
        cmd = manager._compose_cmd("up", "-d", "--build", "--wait")
        assert cmd == [
            "docker", "compose", "-f", "test.yml",
            "up", "-d", "--build", "--wait"
        ]

    def test_compose_cmd_no_args(self):
        """Test compose command with no additional arguments."""
        manager = DockerResourceManager(
            compose_file="compose.yml",
            project_dir="/test",
        )
        cmd = manager._compose_cmd()
        assert cmd == ["docker", "compose", "-f", "compose.yml"]


class TestDockerResourceManagerRun:
    """Tests for _run method."""

    def test_run_successful_command(self):
        """Test _run with successful command."""
        manager = DockerResourceManager(project_dir="/test")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = manager._run("ps")

            assert result.success is True
            assert result.stdout == "success output"
            assert result.stderr == ""
            mock_run.assert_called_once()

    def test_run_failed_command(self):
        """Test _run with failed command."""
        manager = DockerResourceManager(project_dir="/test")

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: container not found"

        with patch("subprocess.run", return_value=mock_result):
            result = manager._run("ps", "nonexistent")

            assert result.success is False
            assert result.exit_code == 1
            assert result.stderr == "error: container not found"

    def test_run_with_timeout(self):
        """Test _run with timeout parameter."""
        manager = DockerResourceManager(project_dir="/test")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            manager._run("build", timeout=300)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 300

    def test_run_timeout_expired(self):
        """Test _run handles TimeoutExpired exception."""
        manager = DockerResourceManager(project_dir="/test")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10)):
            result = manager._run("build", timeout=10)

            assert result.exit_code == 124  # Standard timeout exit code
            assert "timed out" in result.stderr

    def test_run_generic_exception(self):
        """Test _run handles generic exceptions."""
        manager = DockerResourceManager(project_dir="/test")

        with patch("subprocess.run", side_effect=OSError("Docker not found")):
            result = manager._run("ps")

            assert result.exit_code == 1
            assert "Docker not found" in result.stderr

    def test_run_with_cwd(self):
        """Test _run executes command in project directory."""
        manager = DockerResourceManager(project_dir="/my/project")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            manager._run("ps")

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["cwd"] == Path("/my/project")

    def test_run_capture_output(self):
        """Test _run captures output by default."""
        manager = DockerResourceManager(project_dir="/test")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "captured"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            manager._run("ps")

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["capture_output"] is True

    def test_run_with_streaming(self):
        """Test _run with streaming output."""
        manager = DockerResourceManager(project_dir="/test")

        mock_stdout = Mock()
        mock_stdout.readline = Mock(side_effect=["line1\n", "line2\n", ""])

        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = mock_stdout
        mock_process.wait = Mock()

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            with patch("builtins.print"):  # Suppress print output
                result = manager._run("up", stream=True)

                mock_popen.assert_called_once()
                call_kwargs = mock_popen.call_args[1]
                assert call_kwargs["stdout"] == subprocess.PIPE
                assert result.stdout == "line1\nline2\n"

    def test_run_calculates_duration(self):
        """Test _run calculates command duration."""
        manager = DockerResourceManager(project_dir="/test")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = manager._run("ps")

            # Duration should be calculated (even if small)
            assert result.duration >= 0.0

    def test_run_handles_none_stdout_stderr(self):
        """Test _run handles None stdout/stderr from subprocess."""
        manager = DockerResourceManager(project_dir="/test")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = None
        mock_result.stderr = None

        with patch("subprocess.run", return_value=mock_result):
            result = manager._run("ps")

            assert result.stdout == ""
            assert result.stderr == ""


class TestDockerResourceManagerBuild:
    """Tests for build method."""

    def test_build_all_services(self):
        """Test building all services."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="Built", stderr="", duration=30.0
            )

            result = manager.build()

            mock_run.assert_called_once_with("build", "--pull", stream=True)
            assert result.success is True
            assert result.services_built == []

    def test_build_specific_services(self):
        """Test building specific services."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="Built", stderr="", duration=20.0
            )

            result = manager.build(services=["web", "api"])

            mock_run.assert_called_once_with(
                "build", "--pull", "web", "api", stream=True
            )
            assert result.services_built == ["web", "api"]

    def test_build_with_no_cache(self):
        """Test building with --no-cache flag."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=60.0
            )

            manager.build(no_cache=True)

            args = mock_run.call_args[0]
            assert "--no-cache" in args

    def test_build_without_pull(self):
        """Test building without pulling base images."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=10.0
            )

            manager.build(pull=False)

            args = mock_run.call_args[0]
            assert "--pull" not in args

    def test_build_without_streaming(self):
        """Test building without streaming output."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="output", stderr="", duration=5.0
            )

            manager.build(stream=False)

            mock_run.assert_called_once_with("build", "--pull", stream=False)

    def test_build_failure(self):
        """Test build failure handling."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=1,
                stdout="",
                stderr="ERROR: Dockerfile parse error",
                duration=2.0,
            )

            result = manager.build()

            assert result.success is False
            assert result.error == "ERROR: Dockerfile parse error"


class TestDockerResourceManagerUp:
    """Tests for up method."""

    def test_up_default_options(self):
        """Test up with default options (detached)."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=5.0
            )

            result = manager.up()

            mock_run.assert_called_once_with("up", "-d", stream=False)
            assert result.success is True

    def test_up_foreground(self):
        """Test up in foreground mode (not detached)."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=5.0
            )

            manager.up(detach=False)

            args = mock_run.call_args[0]
            assert "-d" not in args
            # Should stream when not detached
            assert mock_run.call_args[1]["stream"] is True

    def test_up_with_build(self):
        """Test up with build flag."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=30.0
            )

            manager.up(build=True)

            args = mock_run.call_args[0]
            assert "--build" in args

    def test_up_with_wait(self):
        """Test up with wait flag."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=60.0
            )

            manager.up(wait=True)

            args = mock_run.call_args[0]
            assert "--wait" in args

    def test_up_with_wait_and_timeout(self):
        """Test up with wait and timeout."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=30.0
            )

            manager.up(wait=True, timeout=120)

            args = mock_run.call_args[0]
            assert "--wait" in args
            assert "--wait-timeout" in args
            assert "120" in args

    def test_up_specific_services(self):
        """Test up with specific services."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=5.0
            )

            manager.up(services=["web", "db"])

            args = mock_run.call_args[0]
            assert "web" in args
            assert "db" in args


class TestDockerResourceManagerDown:
    """Tests for down method."""

    def test_down_default_options(self):
        """Test down with default options."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=5.0
            )

            result = manager.down()

            args = mock_run.call_args[0]
            assert "down" in args
            assert "-t" in args
            assert "10" in args  # default timeout
            assert "--remove-orphans" in args
            assert "-v" not in args  # volumes not removed by default
            assert result.success is True

    def test_down_with_volumes(self):
        """Test down with volumes flag (dangerous operation)."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=5.0
            )

            manager.down(volumes=True)

            args = mock_run.call_args[0]
            assert "-v" in args

    def test_down_without_remove_orphans(self):
        """Test down without removing orphans."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=5.0
            )

            manager.down(remove_orphans=False)

            args = mock_run.call_args[0]
            assert "--remove-orphans" not in args

    def test_down_custom_timeout(self):
        """Test down with custom timeout."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=30.0
            )

            manager.down(timeout=30)

            args = mock_run.call_args[0]
            assert "-t" in args
            idx = args.index("-t")
            assert args[idx + 1] == "30"


class TestDockerResourceManagerExec:
    """Tests for exec method."""

    def test_exec_basic_command(self):
        """Test executing a basic command in container."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="output", stderr="", duration=1.0
            )

            result = manager.exec("web", ["python", "manage.py", "shell"])

            args = mock_run.call_args[0]
            assert "exec" in args
            assert "-T" in args  # No TTY
            assert "web" in args
            assert "python" in args
            assert "manage.py" in args
            assert "shell" in args
            assert result.stdout == "output"

    def test_exec_with_workdir(self):
        """Test exec with working directory."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.exec("web", ["ls"], workdir="/app/src")

            args = mock_run.call_args[0]
            assert "-w" in args
            assert "/app/src" in args

    def test_exec_with_user(self):
        """Test exec with specific user."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.exec("web", ["whoami"], user="root")

            args = mock_run.call_args[0]
            assert "-u" in args
            assert "root" in args

    def test_exec_with_env_vars(self):
        """Test exec with environment variables."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.exec(
                "web",
                ["python", "script.py"],
                env={"DEBUG": "true", "LOG_LEVEL": "debug"},
            )

            args = mock_run.call_args[0]
            assert "-e" in args
            # Check both env vars are passed
            env_args = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
            assert "DEBUG=true" in env_args
            assert "LOG_LEVEL=debug" in env_args

    def test_exec_with_timeout(self):
        """Test exec with timeout."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.exec("web", ["pytest"], timeout=300)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 300

    def test_exec_with_streaming(self):
        """Test exec with streaming output."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.exec("web", ["tail", "-f", "log.txt"], stream=True)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["stream"] is True


class TestDockerResourceManagerLogs:
    """Tests for logs method."""

    def test_logs_default_options(self):
        """Test logs with default options."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="log output", stderr="", duration=1.0
            )

            result = manager.logs()

            args = mock_run.call_args[0]
            assert "logs" in args
            assert "--tail" in args
            assert "100" in args  # default tail
            assert "-f" not in args
            assert "-t" not in args
            assert result.stdout == "log output"

    def test_logs_specific_service(self):
        """Test logs for specific service."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.logs(service="web")

            args = mock_run.call_args[0]
            assert "web" in args

    def test_logs_with_custom_tail(self):
        """Test logs with custom tail count."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.logs(tail=500)

            args = mock_run.call_args[0]
            idx = args.index("--tail")
            assert args[idx + 1] == "500"

    def test_logs_with_follow(self):
        """Test logs with follow flag."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.logs(follow=True)

            args = mock_run.call_args[0]
            assert "-f" in args
            # Should stream when following
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["stream"] is True

    def test_logs_with_timestamps(self):
        """Test logs with timestamps flag."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.logs(timestamps=True)

            args = mock_run.call_args[0]
            assert "-t" in args


class TestDockerResourceManagerPs:
    """Tests for ps method."""

    def test_ps_default(self):
        """Test ps with default options."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0,
                stdout='[{"Name": "web", "State": "running"}]',
                stderr="",
                duration=1.0,
            )

            result = manager.ps()

            args = mock_run.call_args[0]
            assert "ps" in args
            assert "--format" in args
            assert "json" in args
            assert result.success is True

    def test_ps_specific_services(self):
        """Test ps for specific services."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.ps(services=["web", "db"])

            args = mock_run.call_args[0]
            assert "web" in args
            assert "db" in args


class TestDockerResourceManagerIsRunning:
    """Tests for is_running method."""

    def test_is_running_returns_true_when_container_exists(self):
        """Test is_running returns True when container is running."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0,
                stdout="abc123def456",
                stderr="",
                duration=0.5,
            )

            result = manager.is_running("web")

            assert result is True
            mock_run.assert_called_once_with("ps", "-q", "web")

    def test_is_running_returns_false_when_container_not_found(self):
        """Test is_running returns False when container not found."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0,
                stdout="",
                stderr="",
                duration=0.5,
            )

            result = manager.is_running("nonexistent")

            assert result is False

    def test_is_running_returns_false_on_command_failure(self):
        """Test is_running returns False on command failure."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=1,
                stdout="",
                stderr="error",
                duration=0.5,
            )

            result = manager.is_running("web")

            assert result is False

    def test_is_running_handles_whitespace_only_output(self):
        """Test is_running handles whitespace-only output."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0,
                stdout="   \n\t  ",
                stderr="",
                duration=0.5,
            )

            result = manager.is_running("web")

            assert result is False


class TestDockerResourceManagerIsHealthy:
    """Tests for is_healthy method."""

    def test_is_healthy_returns_true_when_healthy(self):
        """Test is_healthy returns True for healthy container."""
        manager = DockerResourceManager(
            project_dir="/test",
            project_name="myproject",
        )

        mock_result = Mock()
        mock_result.stdout = "healthy\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = manager.is_healthy("web")

            assert result is True
            # Check correct container name format
            call_args = mock_run.call_args[0][0]
            assert "myproject-web-1" in call_args

    def test_is_healthy_returns_false_when_unhealthy(self):
        """Test is_healthy returns False for unhealthy container."""
        manager = DockerResourceManager(project_dir="/test", project_name="test")

        mock_result = Mock()
        mock_result.stdout = "unhealthy\n"

        with patch("subprocess.run", return_value=mock_result):
            result = manager.is_healthy("web")

            assert result is False

    def test_is_healthy_returns_false_when_starting(self):
        """Test is_healthy returns False when container is starting."""
        manager = DockerResourceManager(project_dir="/test", project_name="test")

        mock_result = Mock()
        mock_result.stdout = "starting\n"

        with patch("subprocess.run", return_value=mock_result):
            result = manager.is_healthy("web")

            assert result is False

    def test_is_healthy_uses_project_dir_name_when_no_project_name(self):
        """Test is_healthy uses project dir name when project_name not set."""
        manager = DockerResourceManager(project_dir="/my/project")

        mock_result = Mock()
        mock_result.stdout = "healthy\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            manager.is_healthy("api")

            call_args = mock_run.call_args[0][0]
            assert "project-api-1" in call_args

    def test_is_healthy_handles_subprocess_error(self):
        """Test is_healthy handles subprocess errors gracefully."""
        manager = DockerResourceManager(project_dir="/test", project_name="test")

        with patch("subprocess.run", side_effect=subprocess.SubprocessError("error")):
            result = manager.is_healthy("web")

            assert result is False

    def test_is_healthy_handles_os_error(self):
        """Test is_healthy handles OSError gracefully."""
        manager = DockerResourceManager(project_dir="/test", project_name="test")

        with patch("subprocess.run", side_effect=OSError("Docker not found")):
            result = manager.is_healthy("web")

            assert result is False

    def test_is_healthy_handles_file_not_found(self):
        """Test is_healthy handles FileNotFoundError gracefully."""
        manager = DockerResourceManager(project_dir="/test", project_name="test")

        with patch("subprocess.run", side_effect=FileNotFoundError("docker")):
            result = manager.is_healthy("web")

            assert result is False


class TestDockerResourceManagerWaitHealthy:
    """Tests for wait_healthy method."""

    def test_wait_healthy_returns_true_when_healthy(self):
        """Test wait_healthy returns True when service becomes healthy."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8000,
            endpoint="/health/",
            timeout=10,
            initial_delay=0.1,
        )

        mock_response = Mock()
        mock_response.status = 200

        with patch("systemeval.utils.docker.docker_manager.urlopen", return_value=mock_response):
            result = manager.wait_healthy(config)

            assert result is True

    def test_wait_healthy_returns_false_on_timeout(self):
        """Test wait_healthy returns False when timeout reached."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8000,
            timeout=0.5,  # Very short timeout
            initial_delay=0.1,
            max_interval=0.1,
        )

        from urllib.error import URLError
        with patch("systemeval.utils.docker.docker_manager.urlopen", side_effect=URLError("error")):
            result = manager.wait_healthy(config)

            assert result is False

    def test_wait_healthy_retries_on_url_error(self):
        """Test wait_healthy retries on URLError."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8000,
            timeout=5,
            initial_delay=0.1,
            max_interval=0.2,
        )

        mock_response = Mock()
        mock_response.status = 200

        from urllib.error import URLError
        # Fail twice, then succeed
        call_count = [0]
        def mock_urlopen(url, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise URLError("Connection refused")
            return mock_response

        with patch("systemeval.utils.docker.docker_manager.urlopen", side_effect=mock_urlopen):
            result = manager.wait_healthy(config)

            assert result is True
            assert call_count[0] >= 3

    def test_wait_healthy_calls_progress_callback(self):
        """Test wait_healthy calls progress callback."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8000,
            timeout=5,
            initial_delay=0.1,
        )

        mock_response = Mock()
        mock_response.status = 200

        progress_messages = []
        def on_progress(msg):
            progress_messages.append(msg)

        with patch("systemeval.utils.docker.docker_manager.urlopen", return_value=mock_response):
            manager.wait_healthy(config, on_progress=on_progress)

            assert len(progress_messages) > 0
            assert any("healthy" in msg for msg in progress_messages)

    def test_wait_healthy_respects_shutdown_request(self):
        """Test wait_healthy respects shutdown request."""
        manager = DockerResourceManager(project_dir="/test")
        manager._shutdown_requested = True

        config = HealthCheckConfig(
            service="web",
            port=8000,
            timeout=60,
        )

        result = manager.wait_healthy(config)

        assert result is False

    def test_wait_healthy_uses_correct_url(self):
        """Test wait_healthy constructs correct health URL."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8080,
            endpoint="/api/health",
        )

        mock_response = Mock()
        mock_response.status = 200

        with patch("systemeval.utils.docker.docker_manager.urlopen", return_value=mock_response) as mock_url:
            manager.wait_healthy(config)

            call_args = mock_url.call_args[0][0]
            assert call_args == "http://localhost:8080/api/health"

    def test_wait_healthy_handles_non_200_response(self):
        """Test wait_healthy retries on non-200 response."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8000,
            timeout=2,
            initial_delay=0.1,
            max_interval=0.2,
        )

        # Always return 503, should timeout
        mock_response = Mock()
        mock_response.status = 503

        with patch("systemeval.utils.docker.docker_manager.urlopen", return_value=mock_response):
            result = manager.wait_healthy(config)

            assert result is False

    def test_wait_healthy_exponential_backoff(self):
        """Test wait_healthy uses exponential backoff."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8000,
            timeout=3,
            initial_delay=0.1,
            max_interval=0.5,
        )

        from urllib.error import URLError

        sleep_times = []
        original_sleep = time.sleep

        def mock_sleep(seconds):
            sleep_times.append(seconds)
            original_sleep(0.01)  # Actually sleep a tiny bit

        with patch("systemeval.utils.docker.docker_manager.urlopen", side_effect=URLError("error")):
            with patch("systemeval.utils.docker.docker_manager.time.sleep", side_effect=mock_sleep):
                manager.wait_healthy(config)

        # Verify backoff increases (with cap)
        if len(sleep_times) >= 2:
            # Initial delay should increase (multiply by 1.5 each time)
            assert sleep_times[1] >= sleep_times[0]

    def test_wait_healthy_handles_generic_exception(self):
        """Test wait_healthy handles generic exceptions."""
        manager = DockerResourceManager(project_dir="/test")
        config = HealthCheckConfig(
            service="web",
            port=8000,
            timeout=1,
            initial_delay=0.1,
        )

        progress_messages = []
        def on_progress(msg):
            progress_messages.append(msg)

        with patch("systemeval.utils.docker.docker_manager.urlopen", side_effect=Exception("unexpected error")):
            result = manager.wait_healthy(config, on_progress=on_progress)

            # Should handle exception and continue retrying
            assert result is False
            # Should report the error
            assert any("error" in msg.lower() for msg in progress_messages)


class TestDockerResourceManagerSignalHandlers:
    """Tests for signal handler methods."""

    def test_install_signal_handlers_sets_handlers(self):
        """Test install_signal_handlers sets SIGINT and SIGTERM handlers."""
        manager = DockerResourceManager(project_dir="/test")
        cleanup_called = [False]

        def cleanup():
            cleanup_called[0] = True

        # Save original handlers
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        try:
            manager.install_signal_handlers(cleanup)

            # Verify handlers were saved
            assert manager._original_sigint == original_sigint
            assert manager._original_sigterm == original_sigterm

            # Verify new handlers are installed (they should be different)
            current_sigint = signal.getsignal(signal.SIGINT)
            assert current_sigint != original_sigint
        finally:
            # Restore handlers
            manager.restore_signal_handlers()

    def test_restore_signal_handlers_restores_original(self):
        """Test restore_signal_handlers restores original handlers."""
        manager = DockerResourceManager(project_dir="/test")

        # Save original handlers
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        try:
            manager.install_signal_handlers(lambda: None)
            manager.restore_signal_handlers()

            # Verify handlers are restored
            assert signal.getsignal(signal.SIGINT) == original_sigint
            assert signal.getsignal(signal.SIGTERM) == original_sigterm
            assert manager._shutdown_requested is False
        finally:
            # Ensure we're back to original state
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

    def test_restore_signal_handlers_handles_no_prior_install(self):
        """Test restore_signal_handlers handles case where install was never called."""
        manager = DockerResourceManager(project_dir="/test")

        # Should not raise even if install was never called
        manager.restore_signal_handlers()

        assert manager._shutdown_requested is False

    def test_signal_handler_sets_shutdown_flag(self):
        """Test signal handler sets _shutdown_requested flag."""
        manager = DockerResourceManager(project_dir="/test")
        cleanup_called = [False]

        def cleanup():
            cleanup_called[0] = True

        original_sigint = signal.getsignal(signal.SIGINT)

        try:
            manager.install_signal_handlers(cleanup)

            # Get the installed handler
            handler = signal.getsignal(signal.SIGINT)

            # Call the handler (simulate SIGINT)
            try:
                handler(signal.SIGINT, None)
            except KeyboardInterrupt:
                pass  # Expected

            assert manager._shutdown_requested is True
            assert cleanup_called[0] is True
        finally:
            signal.signal(signal.SIGINT, original_sigint)
            manager._shutdown_requested = False

    def test_signal_handler_sigterm_raises_systemexit(self):
        """Test SIGTERM handler raises SystemExit."""
        manager = DockerResourceManager(project_dir="/test")

        original_sigterm = signal.getsignal(signal.SIGTERM)

        try:
            manager.install_signal_handlers(lambda: None)

            handler = signal.getsignal(signal.SIGTERM)

            with pytest.raises(SystemExit) as exc_info:
                handler(signal.SIGTERM, None)

            # Exit code should be 128 + signal number
            assert exc_info.value.code == 128 + signal.SIGTERM
        finally:
            signal.signal(signal.SIGTERM, original_sigterm)


class TestDockerResourceManagerIntegration:
    """Integration tests for DockerResourceManager."""

    def test_full_lifecycle_workflow(self):
        """Test typical workflow: build, up, exec, logs, down."""
        manager = DockerResourceManager(
            compose_file="docker-compose.yml",
            project_dir="/test/project",
            project_name="testproject",
        )

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="success", stderr="", duration=1.0
            )

            # Build
            build_result = manager.build(services=["web"])
            assert build_result.success is True

            # Up
            up_result = manager.up(services=["web"], detach=True)
            assert up_result.success is True

            # Exec
            exec_result = manager.exec("web", ["python", "manage.py", "migrate"])
            assert exec_result.success is True

            # Logs
            logs_result = manager.logs(service="web")
            assert logs_result.success is True

            # Down
            down_result = manager.down()
            assert down_result.success is True

            # Verify all operations were called
            assert mock_run.call_count == 5

    def test_error_recovery_workflow(self):
        """Test error handling during workflow."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            # Simulate build failure
            mock_run.return_value = CommandResult(
                exit_code=1,
                stdout="",
                stderr="Dockerfile not found",
                duration=2.0,
            )

            build_result = manager.build()

            assert build_result.success is False
            assert "Dockerfile" in build_result.error

    def test_compose_command_includes_all_options(self):
        """Test compose command includes file, project name, and args."""
        manager = DockerResourceManager(
            compose_file="local.yml",
            project_dir="/my/project",
            project_name="myapp",
        )

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            manager.up(services=["web"], build=True, wait=True)

            # The _compose_cmd is called internally, check the args passed to _run
            call_args = mock_run.call_args[0]
            # Args should include: up, -d, --build, --wait, web
            assert "up" in call_args
            assert "-d" in call_args
            assert "--build" in call_args
            assert "--wait" in call_args
            assert "web" in call_args


class TestDockerResourceManagerEdgeCases:
    """Edge case tests for DockerResourceManager."""

    def test_empty_service_list(self):
        """Test operations with empty service list."""
        manager = DockerResourceManager(project_dir="/test")

        with patch.object(manager, "_run") as mock_run:
            mock_run.return_value = CommandResult(
                exit_code=0, stdout="", stderr="", duration=1.0
            )

            # Empty list should be treated same as None (all services)
            manager.up(services=[])

            args = mock_run.call_args[0]
            # Should not have any service names appended
            assert args == ("up", "-d")

    def test_special_characters_in_project_name(self):
        """Test project name with special characters."""
        manager = DockerResourceManager(
            project_dir="/test",
            project_name="my-project_v2.0",
        )

        cmd = manager._compose_cmd("up")
        assert "-p" in cmd
        assert "my-project_v2.0" in cmd

    def test_long_running_command_duration_tracking(self):
        """Test duration is tracked correctly for long commands."""
        manager = DockerResourceManager(project_dir="/test")

        def slow_run(*args, **kwargs):
            time.sleep(0.1)  # Simulate some work
            return Mock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=slow_run):
            result = manager._run("ps")

            # Duration should be at least 0.1 seconds
            assert result.duration >= 0.1

    def test_unicode_in_output(self):
        """Test handling of unicode characters in output."""
        manager = DockerResourceManager(project_dir="/test")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Container started: \u2713 web"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = manager._run("ps")

            assert "\u2713" in result.stdout

    def test_very_large_output(self):
        """Test handling of very large output."""
        manager = DockerResourceManager(project_dir="/test")

        large_output = "x" * 1000000  # 1MB of output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = large_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = manager._run("logs")

            assert len(result.stdout) == 1000000

    def test_path_with_spaces(self):
        """Test project directory with spaces in path."""
        manager = DockerResourceManager(project_dir="/my project/dir")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            manager._run("ps")

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["cwd"] == Path("/my project/dir")
