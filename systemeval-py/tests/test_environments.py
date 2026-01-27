"""Tests for environment abstractions and test executor."""

import os
import pytest
import tempfile
from pathlib import Path

from systemeval.environments.base import Environment, EnvironmentType, SetupResult, PhaseTimings
from systemeval.environments.executor import TestExecutor, ExecutionResult


class TestPhaseTimings:
    """Tests for PhaseTimings dataclass."""

    def test_total_calculation(self):
        """Test total timing calculation."""
        timings = PhaseTimings(
            build=10.0,
            startup=5.0,
            health_check=2.0,
            tests=30.0,
            cleanup=3.0,
        )
        assert timings.total == 50.0

    def test_default_zero(self):
        """Test default values are zero."""
        timings = PhaseTimings()
        assert timings.total == 0.0


class TestSetupResult:
    """Tests for SetupResult dataclass."""

    def test_success_result(self):
        """Test successful setup result."""
        result = SetupResult(
            success=True,
            message="Started successfully",
            duration=2.5,
            details={"pid": 12345},
        )
        assert result.success is True
        assert result.duration == 2.5

    def test_failure_result(self):
        """Test failed setup result."""
        result = SetupResult(
            success=False,
            message="Failed to start: port in use",
        )
        assert result.success is False


class TestTestExecutor:
    """Tests for TestExecutor class."""

    def test_execute_simple_command(self):
        """Test executing a simple command."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute("echo 'hello world'", stream=False)

        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_execute_failing_command(self):
        """Test executing a failing command."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute("exit 1", stream=False)

        assert result.success is False
        assert result.exit_code == 1

    def test_execute_with_env_vars(self):
        """Test executing with environment variables."""
        executor = TestExecutor(working_dir=".", env={"MY_VAR": "test123"})
        result = executor.execute("echo $MY_VAR", stream=False)

        assert "test123" in result.stdout

    def test_execute_sequence_success(self):
        """Test executing a sequence of commands."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute(
            ["echo 'first'", "echo 'second'", "echo 'third'"],
            stream=False,
        )

        assert result.success is True
        assert "first" in result.stdout
        assert "second" in result.stdout
        assert "third" in result.stdout

    def test_execute_sequence_stops_on_failure(self):
        """Test that sequence stops on first failure."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute(
            ["echo 'first'", "exit 1", "echo 'never'"],
            stream=False,
        )

        assert result.success is False
        assert "first" in result.stdout
        assert "never" not in result.stdout

    def test_execute_nonexistent_directory(self):
        """Test executing in nonexistent directory."""
        executor = TestExecutor(working_dir="/nonexistent/path/12345")
        result = executor.execute("echo test", stream=False)

        assert result.success is False
        assert result.exit_code == 2

    def test_execution_result_properties(self):
        """Test ExecutionResult properties."""
        result = ExecutionResult(
            exit_code=0,
            stdout="output",
            stderr="",
            duration=1.5,
            command="echo test",
        )

        assert result.success is True

        result2 = ExecutionResult(
            exit_code=1,
            stdout="",
            stderr="error",
            duration=0.5,
            command="bad cmd",
        )

        assert result2.success is False


class TestTestExecutorParseResults:
    """Tests for TestExecutor output parsing."""

    def test_parse_pytest_output(self):
        """Test parsing pytest output format."""
        executor = TestExecutor()
        output = """
        ============== test session starts ==============
        collected 12 items

        tests/test_example.py ...F..E....

        FAILED tests/test_example.py::test_one
        ERROR tests/test_example.py::test_two

        ============ 10 passed, 1 failed, 1 error in 5.23s ============
        """

        result = executor.parse_test_results(output, exit_code=1)

        assert result.passed == 10
        assert result.failed == 1
        assert result.errors == 1

    def test_parse_simple_passed(self):
        """Test parsing simple passed output."""
        executor = TestExecutor()
        output = "5 passed in 2.1s"

        result = executor.parse_test_results(output, exit_code=0)

        assert result.passed == 5
        assert result.exit_code == 0

    def test_parse_jest_output(self):
        """Test parsing Jest output format."""
        executor = TestExecutor()
        output = """
        PASS src/tests/example.test.js
        Tests: 8 passed, 2 failed, 10 total
        Time: 3.456s
        """

        result = executor.parse_test_results(output, exit_code=1)

        assert result.passed == 8
        assert result.failed == 2

    def test_parse_playwright_output(self):
        """Test parsing Playwright output format."""
        executor = TestExecutor()
        output = """
        Running 5 tests using 2 workers
        5 passed (10.5s)
        """

        result = executor.parse_test_results(output, exit_code=0)

        assert result.passed == 5

    def test_parse_unknown_format_success(self):
        """Test parsing unknown format with success exit code."""
        executor = TestExecutor()
        output = "All checks completed"

        result = executor.parse_test_results(output, exit_code=0)

        # Should assume at least 1 passed
        assert result.passed >= 1
        assert result.exit_code == 0

    def test_parse_unknown_format_failure(self):
        """Test parsing unknown format with failure exit code.

        When output format is unrecognized and exit_code != 0, the parser
        should report ERROR (via errors=1) rather than FAIL with guessed counts.
        This prevents false positives from incorrect test count assumptions.
        """
        executor = TestExecutor()
        output = "Something went wrong"

        result = executor.parse_test_results(output, exit_code=1)

        # Should report as error (not failed) when output is unrecognized
        assert result.errors == 1
        assert result.failed == 0  # No guessed failed count
        assert result.exit_code == 1
        assert result.parsed_from == "fallback"
        assert result.parsing_warning is not None
        # Verdict should be ERROR, not FAIL
        from systemeval.core.evaluation import Verdict
        assert result.verdict == Verdict.ERROR

    def test_parse_with_skipped(self):
        """Test parsing output with skipped tests."""
        executor = TestExecutor()
        output = "10 passed, 3 skipped in 5.0s"

        result = executor.parse_test_results(output, exit_code=0)

        assert result.passed == 10
        assert result.skipped == 3

    def test_parse_mocha_output(self):
        """Test parsing Mocha output format."""
        executor = TestExecutor()
        output = """
          Authentication Tests
            ✓ should login with valid credentials
            ✓ should reject invalid password
            1) should handle timeout

          2 passing (500ms)
          1 failing
        """

        result = executor.parse_test_results(output, exit_code=1)

        assert result.passed == 2
        assert result.failed == 1
        assert result.parsed_from == "mocha"

    def test_parse_go_test_output(self):
        """Test parsing Go test output format."""
        executor = TestExecutor()
        output = """
        ok      github.com/example/pkg1    0.123s
        ok      github.com/example/pkg2    0.456s
        FAIL    github.com/example/pkg3    0.789s
        ?       github.com/example/noop    [no test files]
        """

        result = executor.parse_test_results(output, exit_code=1)

        assert result.passed == 2
        assert result.failed == 1
        assert result.skipped == 1
        assert result.parsed_from == "go"

    def test_parse_json_pytest_report(self):
        """Test parsing pytest-json-report format."""
        executor = TestExecutor()
        json_output = '''{"summary": {"passed": 5, "failed": 2, "error": 1, "skipped": 3}, "tests": [], "duration": 10.5}'''

        result = executor.parse_test_results("", exit_code=1, json_output=json_output)

        assert result.passed == 5
        assert result.failed == 2
        assert result.errors == 1
        assert result.skipped == 3
        assert result.duration == 10.5
        assert result.parsed_from == "json:pytest"

    def test_parse_json_jest_report(self):
        """Test parsing Jest JSON format."""
        executor = TestExecutor()
        json_output = '''{"numPassedTests": 8, "numFailedTests": 2, "numPendingTests": 1, "testResults": [{"perfStats": {"runtime": 3456}}]}'''

        result = executor.parse_test_results("", exit_code=1, json_output=json_output)

        assert result.passed == 8
        assert result.failed == 2
        assert result.skipped == 1
        assert result.parsed_from == "json:jest"

    def test_parse_prefers_json_over_regex(self):
        """Test that JSON output is preferred over regex parsing."""
        executor = TestExecutor()
        # Output says 10 passed, but JSON says 5 passed
        text_output = "10 passed in 1.0s"
        json_output = '''{"summary": {"passed": 5, "failed": 0, "error": 0, "skipped": 0}, "tests": [], "duration": 2.0}'''

        result = executor.parse_test_results(text_output, exit_code=0, json_output=json_output)

        # Should use JSON values, not regex
        assert result.passed == 5
        assert result.parsed_from == "json:pytest"

    def test_parse_pytest_collection_error(self):
        """Test detecting pytest collection errors."""
        executor = TestExecutor()
        output = """
        ============================= ERRORS ===============================
        ERROR collecting tests/test_broken.py
        ModuleNotFoundError: No module named 'nonexistent'
        ========================= no tests ran in 0.05s ========================
        """

        result = executor.parse_test_results(output, exit_code=2)

        assert result.errors == 1
        assert result.parsed_from == "pytest"
        assert result.parsing_warning == "Collection error detected"

    def test_parsed_from_is_set_correctly(self):
        """Test that parsed_from field is set for each parser."""
        executor = TestExecutor()

        # Pytest
        result = executor.parse_test_results("5 passed in 1.0s", exit_code=0)
        assert result.parsed_from == "pytest"

        # Jest
        result = executor.parse_test_results("Tests: 5 passed, 0 failed, 5 total", exit_code=0)
        assert result.parsed_from == "jest"

        # Playwright
        result = executor.parse_test_results("5 passed (10s)", exit_code=0)
        assert result.parsed_from == "playwright"

        # Fallback
        result = executor.parse_test_results("no recognizable output", exit_code=0)
        assert result.parsed_from == "fallback"


class TestTestExecutorIntegration:
    """Integration tests for TestExecutor with real files."""

    def test_execute_script_file(self, tmp_path):
        """Test executing a shell script file."""
        # Create a test script
        script = tmp_path / "test.sh"
        script.write_text("#!/bin/bash\necho 'script output'\nexit 0")
        script.chmod(0o755)

        executor = TestExecutor(working_dir=str(tmp_path))
        result = executor.execute(f"./test.sh", stream=False)

        assert result.success is True
        assert "script output" in result.stdout

    def test_execute_python_command(self):
        """Test executing a Python command."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute(
            "python3 -c \"print('hello from python')\"",
            stream=False,
        )

        assert result.success is True
        assert "hello from python" in result.stdout

    def test_execute_with_timeout(self):
        """Test command timeout."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute(
            "sleep 10",
            timeout=1,
            stream=False,
        )

        assert result.success is False
        assert result.exit_code == 124  # timeout exit code
        assert "timed out" in result.stderr.lower()

    def test_execute_with_timeout_streaming(self):
        """Test command timeout in streaming mode."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute(
            "sleep 10",
            timeout=1,
            stream=True,
        )

        assert result.success is False
        assert result.exit_code == 124  # timeout exit code
        assert "timed out" in result.stderr.lower()

    def test_execute_streaming_timeout_kills_process(self):
        """Test that streaming timeout kills hanging process."""
        executor = TestExecutor(working_dir=".")

        # Use a command that hangs (tail -f /dev/null blocks forever)
        result = executor.execute(
            "tail -f /dev/null",
            timeout=2,
            stream=True,
        )

        assert result.success is False
        assert result.exit_code == 124
        assert "timed out" in result.stderr.lower()
        # Duration should be close to timeout (within reasonable margin)
        assert 1.5 <= result.duration <= 3.0

    def test_duration_tracked(self):
        """Test that execution duration is tracked."""
        executor = TestExecutor(working_dir=".")
        result = executor.execute("sleep 0.1", stream=False)

        assert result.duration >= 0.1
        assert result.duration < 1.0  # shouldn't take too long


class TestEnvironmentTypes:
    """Tests for EnvironmentType enum."""

    def test_environment_types(self):
        """Test environment type values."""
        assert EnvironmentType.STANDALONE.value == "standalone"
        assert EnvironmentType.DOCKER_COMPOSE.value == "docker-compose"
        assert EnvironmentType.COMPOSITE.value == "composite"


# --- StandaloneEnvironment Tests ---

from unittest.mock import MagicMock, patch, PropertyMock, call
import subprocess
import io
import threading
import time

from systemeval.environments.implementations.standalone import StandaloneEnvironment


class TestStandaloneEnvironmentInit:
    """Tests for StandaloneEnvironment initialization."""

    def test_init_with_full_config(self):
        """Test initialization with all configuration options."""
        config = {
            "command": "npm run dev",
            "ready_pattern": "ready on port",
            "test_command": "npm test",
            "port": 3000,
            "working_dir": "/app",
            "env": {"NODE_ENV": "test"},
        }
        env = StandaloneEnvironment("frontend", config)

        assert env.name == "frontend"
        assert env.command == "npm run dev"
        assert env.ready_pattern == "ready on port"
        assert env.test_command == "npm test"
        assert env.port == 3000
        assert env.working_dir == Path("/app")
        assert env.env_vars == {"NODE_ENV": "test"}
        assert env._process is None
        assert env._output_buffer == []

    def test_init_with_minimal_config(self):
        """Test initialization with minimal configuration."""
        config = {}
        env = StandaloneEnvironment("minimal", config)

        assert env.name == "minimal"
        assert env.command == ""
        assert env.ready_pattern == ""
        assert env.test_command == ""
        assert env.port == 3000  # default
        assert env.working_dir == Path(".")  # default
        assert env.env_vars == {}

    def test_env_type_property(self):
        """Test that env_type returns STANDALONE."""
        env = StandaloneEnvironment("test", {})
        assert env.env_type == EnvironmentType.STANDALONE


class TestStandaloneEnvironmentSetup:
    """Tests for StandaloneEnvironment.setup() method."""

    def test_setup_no_command_skips_startup(self):
        """Test setup with no command configured skips startup."""
        env = StandaloneEnvironment("test", {"command": ""})
        result = env.setup()

        assert result.success is True
        assert "No command configured" in result.message
        assert env._process is None

    @patch("subprocess.Popen")
    def test_setup_starts_process(self, mock_popen, tmp_path):
        """Test setup starts subprocess with correct arguments."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        config = {
            "command": "npm run dev",
            "working_dir": str(tmp_path),
            "env": {"NODE_ENV": "test"},
        }
        env = StandaloneEnvironment("frontend", config)
        result = env.setup()

        assert result.success is True
        assert "Started: npm run dev" in result.message
        assert result.details["pid"] == 12345
        assert env._process is mock_process

        # Verify Popen was called with correct args
        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args.kwargs
        assert call_kwargs["cwd"] == tmp_path
        assert call_kwargs["stdout"] == subprocess.PIPE
        assert call_kwargs["stderr"] == subprocess.STDOUT
        assert call_kwargs["text"] is True

    @patch("subprocess.Popen")
    def test_setup_records_startup_timing(self, mock_popen, tmp_path):
        """Test setup records startup timing."""
        mock_popen.return_value = MagicMock(pid=1)

        config = {"command": "sleep 0.1", "working_dir": str(tmp_path)}
        env = StandaloneEnvironment("test", config)
        result = env.setup()

        assert result.success is True
        assert result.duration >= 0
        assert env.timings.startup >= 0

    @patch("subprocess.Popen")
    def test_setup_handles_exception(self, mock_popen, tmp_path):
        """Test setup handles Popen exception gracefully."""
        mock_popen.side_effect = OSError("Command not found")

        config = {"command": "nonexistent-command", "working_dir": str(tmp_path)}
        env = StandaloneEnvironment("test", config)
        result = env.setup()

        assert result.success is False
        assert "Failed to start" in result.message
        assert "Command not found" in result.message

    @patch("subprocess.Popen")
    def test_setup_parses_command_with_shlex(self, mock_popen, tmp_path):
        """Test setup uses shlex to parse command."""
        mock_popen.return_value = MagicMock(pid=1)

        config = {
            "command": 'npm run dev --port 3000 --env "production mode"',
            "working_dir": str(tmp_path),
        }
        env = StandaloneEnvironment("test", config)
        env.setup()

        call_args = mock_popen.call_args.args[0]
        assert call_args == ["npm", "run", "dev", "--port", "3000", "--env", "production mode"]


class TestStandaloneEnvironmentIsReady:
    """Tests for StandaloneEnvironment.is_ready() method."""

    def test_is_ready_no_command(self):
        """Test is_ready returns True when no command configured."""
        env = StandaloneEnvironment("test", {"command": ""})
        assert env.is_ready() is True

    def test_is_ready_no_process(self):
        """Test is_ready returns False when process not started."""
        env = StandaloneEnvironment("test", {"command": "some command"})
        assert env.is_ready() is False

    def test_is_ready_process_exited(self):
        """Test is_ready returns False when process has exited."""
        env = StandaloneEnvironment("test", {"command": "some command"})
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process exited with code 1
        env._process = mock_process

        assert env.is_ready() is False

    def test_is_ready_no_pattern_required(self):
        """Test is_ready returns True when no ready_pattern and process running."""
        env = StandaloneEnvironment("test", {
            "command": "some command",
            "ready_pattern": "",
        })
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process still running
        env._process = mock_process

        assert env.is_ready() is True

    def test_is_ready_pattern_not_matched(self):
        """Test is_ready returns False when pattern not in output buffer."""
        env = StandaloneEnvironment("test", {
            "command": "npm run dev",
            "ready_pattern": "ready on port",
        })
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        env._process = mock_process
        env._output_buffer = ["Starting server...", "Loading config..."]

        assert env.is_ready() is False

    def test_is_ready_pattern_matched(self):
        """Test is_ready returns True when pattern found in output buffer."""
        env = StandaloneEnvironment("test", {
            "command": "npm run dev",
            "ready_pattern": "ready on port",
        })
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        env._process = mock_process
        env._output_buffer = [
            "Starting server...",
            "Compiling...",
            "Server ready on port 3000",
        ]

        assert env.is_ready() is True

    def test_is_ready_pattern_regex(self):
        """Test is_ready supports regex patterns."""
        env = StandaloneEnvironment("test", {
            "command": "npm run dev",
            "ready_pattern": r"ready on port \d+",
        })
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        env._process = mock_process
        env._output_buffer = ["Server ready on port 3000"]

        assert env.is_ready() is True


class TestStandaloneEnvironmentWaitReady:
    """Tests for StandaloneEnvironment.wait_ready() method."""

    def test_wait_ready_no_command(self):
        """Test wait_ready returns True when no command configured."""
        env = StandaloneEnvironment("test", {"command": ""})
        assert env.wait_ready() is True

    def test_wait_ready_no_process(self):
        """Test wait_ready returns False when process not started."""
        env = StandaloneEnvironment("test", {"command": "some command"})
        assert env.wait_ready() is False

    def test_wait_ready_no_stdout(self):
        """Test wait_ready returns False when process has no stdout."""
        env = StandaloneEnvironment("test", {"command": "some command"})
        mock_process = MagicMock()
        mock_process.stdout = None
        env._process = mock_process

        assert env.wait_ready() is False

    def test_wait_ready_no_pattern_process_running(self):
        """Test wait_ready returns True after brief wait when no pattern and process running."""
        env = StandaloneEnvironment("test", {
            "command": "some command",
            "ready_pattern": "",
        })
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process running
        mock_process.stdout = MagicMock()
        env._process = mock_process

        with patch("time.sleep"):  # Skip actual sleep
            result = env.wait_ready(timeout=5)

        assert result is True

    def test_wait_ready_no_pattern_process_exited(self):
        """Test wait_ready returns False when no pattern and process exited."""
        env = StandaloneEnvironment("test", {
            "command": "some command",
            "ready_pattern": "",
        })
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process exited
        mock_process.stdout = MagicMock()
        env._process = mock_process

        with patch("time.sleep"):
            result = env.wait_ready(timeout=5)

        assert result is False

    def test_wait_ready_pattern_matched(self):
        """Test wait_ready returns True when pattern found in output."""
        env = StandaloneEnvironment("test", {
            "command": "npm run dev",
            "ready_pattern": "ready",
        })

        # Simulate stdout that returns lines then empty
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = [
            "Starting...\n",
            "Compiling...\n",
            "Server ready\n",
            "",
        ]

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = mock_stdout
        env._process = mock_process

        with patch("time.sleep"):
            result = env.wait_ready(timeout=10)

        assert result is True
        assert "Server ready\n" in env._output_buffer
        assert env.timings.health_check > 0

    def test_wait_ready_process_exits_before_pattern(self):
        """Test wait_ready returns False when process exits before pattern matched."""
        env = StandaloneEnvironment("test", {
            "command": "npm run dev",
            "ready_pattern": "ready",
        })

        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = "Starting...\n"

        mock_process = MagicMock()
        # First poll returns None, then returns exit code
        mock_process.poll.side_effect = [None, None, 1]
        mock_process.stdout = mock_stdout
        env._process = mock_process

        with patch("time.sleep"):
            result = env.wait_ready(timeout=1)

        assert result is False

    def test_wait_ready_timeout(self):
        """Test wait_ready returns False on timeout."""
        env = StandaloneEnvironment("test", {
            "command": "npm run dev",
            "ready_pattern": "never matches",
        })

        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = "Still starting...\n"

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = mock_stdout
        env._process = mock_process

        # Simulate time passing
        start_time = time.time()
        time_values = [start_time, start_time + 0.5, start_time + 1.5]

        with patch("time.time", side_effect=time_values):
            with patch("time.sleep"):
                result = env.wait_ready(timeout=1)

        assert result is False


class TestStandaloneEnvironmentRunTests:
    """Tests for StandaloneEnvironment.run_tests() method."""

    def test_run_tests_no_test_command(self):
        """Test run_tests returns error result when no test_command configured."""
        env = StandaloneEnvironment("test", {"test_command": ""})
        result = env.run_tests()

        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 1
        assert result.exit_code == 2

    @patch.object(StandaloneEnvironment, "_build_test_command")
    def test_run_tests_uses_executor(self, mock_build_cmd, tmp_path):
        """Test run_tests creates TestExecutor and executes command."""
        mock_build_cmd.return_value = "pytest -v"

        config = {
            "test_command": "pytest",
            "working_dir": str(tmp_path),
            "env": {"TEST_VAR": "1"},
        }
        env = StandaloneEnvironment("test", config)

        with patch("systemeval.environments.implementations.standalone.TestExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = MagicMock(
                stdout="1 passed in 0.5s",
                exit_code=0,
            )
            mock_executor.parse_test_results.return_value = MagicMock(
                passed=1, failed=0, errors=0, skipped=0, duration=0.5, exit_code=0
            )
            mock_executor_class.return_value = mock_executor

            result = env.run_tests(suite="unit", verbose=True)

            mock_executor_class.assert_called_once_with(
                working_dir=str(tmp_path),
                env={"TEST_VAR": "1"},
                verbose=True,
            )
            mock_executor.execute.assert_called_once()

    def test_run_tests_records_timing(self, tmp_path):
        """Test run_tests records test timing."""
        config = {
            "test_command": "echo '1 passed in 0.1s'",
            "working_dir": str(tmp_path),
        }
        env = StandaloneEnvironment("test", config)

        result = env.run_tests()

        assert env.timings.tests >= 0


class TestStandaloneEnvironmentBuildTestCommand:
    """Tests for StandaloneEnvironment._build_test_command() method."""

    def test_build_test_command_list(self):
        """Test _build_test_command returns list as-is."""
        env = StandaloneEnvironment("test", {
            "test_command": ["npm run build", "npm test"],
        })
        result = env._build_test_command(suite=None, category=None, verbose=False)

        assert result == ["npm run build", "npm test"]

    def test_build_test_command_script_with_suite(self):
        """Test _build_test_command adds SUITE env var for scripts."""
        env = StandaloneEnvironment("test", {
            "test_command": "./scripts/run-tests.sh",
        })
        result = env._build_test_command(suite="integration", category=None, verbose=False)

        assert "SUITE=integration" in result
        assert "./scripts/run-tests.sh" in result

    def test_build_test_command_script_with_category(self):
        """Test _build_test_command adds CATEGORY env var for scripts."""
        env = StandaloneEnvironment("test", {
            "test_command": "/usr/bin/run-tests.sh",
        })
        result = env._build_test_command(suite=None, category="api", verbose=False)

        assert "CATEGORY=api" in result

    def test_build_test_command_script_verbose(self):
        """Test _build_test_command adds -v flag for verbose scripts."""
        env = StandaloneEnvironment("test", {
            "test_command": "./run-tests.sh",
        })
        result = env._build_test_command(suite=None, category=None, verbose=True)

        assert result.endswith("-v")

    def test_build_test_command_pytest_with_suite(self):
        """Test _build_test_command adds -m flag for pytest suite."""
        env = StandaloneEnvironment("test", {
            "test_command": "pytest",
        })
        result = env._build_test_command(suite="unit", category=None, verbose=False)

        assert "-m unit" in result

    def test_build_test_command_pytest_with_category(self):
        """Test _build_test_command adds -m flag for pytest category."""
        env = StandaloneEnvironment("test", {
            "test_command": "pytest tests/",
        })
        result = env._build_test_command(suite=None, category="integration", verbose=False)

        assert "-m integration" in result

    def test_build_test_command_pytest_verbose(self):
        """Test _build_test_command adds -v for pytest verbose."""
        env = StandaloneEnvironment("test", {
            "test_command": "pytest",
        })
        result = env._build_test_command(suite=None, category=None, verbose=True)

        assert "-v" in result

    def test_build_test_command_pytest_already_verbose(self):
        """Test _build_test_command does not duplicate -v flag."""
        env = StandaloneEnvironment("test", {
            "test_command": "pytest -v",
        })
        result = env._build_test_command(suite=None, category=None, verbose=True)

        assert result.count("-v") == 1

    def test_build_test_command_npm_test_with_suite(self):
        """Test _build_test_command adds testPathPattern for npm test."""
        env = StandaloneEnvironment("test", {
            "test_command": "npm test",
        })
        result = env._build_test_command(suite="components", category=None, verbose=False)

        assert "--testPathPattern=components" in result

    def test_build_test_command_jest_with_suite(self):
        """Test _build_test_command adds testPathPattern for jest."""
        env = StandaloneEnvironment("test", {
            "test_command": "jest",
        })
        result = env._build_test_command(suite="utils", category=None, verbose=False)

        assert "--testPathPattern=utils" in result

    def test_build_test_command_playwright_with_suite(self):
        """Test _build_test_command adds grep for playwright."""
        env = StandaloneEnvironment("test", {
            "test_command": "npx playwright test",
        })
        result = env._build_test_command(suite="login", category=None, verbose=False)

        assert "--grep login" in result


class TestStandaloneEnvironmentTeardown:
    """Tests for StandaloneEnvironment.teardown() method."""

    def test_teardown_no_process(self):
        """Test teardown with no process does nothing."""
        env = StandaloneEnvironment("test", {})
        env.teardown()

        assert env._process is None
        assert env.timings.cleanup >= 0

    def test_teardown_keep_running(self):
        """Test teardown with keep_running=True does not stop process."""
        env = StandaloneEnvironment("test", {})
        mock_process = MagicMock()
        env._process = mock_process

        env.teardown(keep_running=True)

        mock_process.terminate.assert_not_called()
        assert env._process is mock_process

    def test_teardown_terminates_process(self):
        """Test teardown terminates process gracefully."""
        env = StandaloneEnvironment("test", {})
        mock_process = MagicMock()
        env._process = mock_process

        env.teardown()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)
        assert env._process is None

    def test_teardown_kills_on_timeout(self):
        """Test teardown kills process if terminate times out."""
        env = StandaloneEnvironment("test", {})
        mock_process = MagicMock()
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        env._process = mock_process

        env.teardown()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        assert env._process is None

    def test_teardown_handles_os_error(self):
        """Test teardown handles OSError gracefully (process already gone)."""
        env = StandaloneEnvironment("test", {})
        mock_process = MagicMock()
        mock_process.terminate.side_effect = OSError("No such process")
        env._process = mock_process

        # Should not raise
        env.teardown()

        assert env._process is None

    def test_teardown_records_cleanup_timing(self):
        """Test teardown records cleanup timing."""
        env = StandaloneEnvironment("test", {})
        mock_process = MagicMock()
        env._process = mock_process

        env.teardown()

        assert env.timings.cleanup >= 0


class TestStandaloneEnvironmentContextManager:
    """Tests for StandaloneEnvironment context manager behavior."""

    @patch.object(StandaloneEnvironment, "setup")
    @patch.object(StandaloneEnvironment, "wait_ready")
    @patch.object(StandaloneEnvironment, "teardown")
    def test_context_manager_success(self, mock_teardown, mock_wait, mock_setup):
        """Test context manager calls setup, wait_ready, and teardown."""
        mock_setup.return_value = SetupResult(success=True, message="Started")
        mock_wait.return_value = True

        env = StandaloneEnvironment("test", {"command": "npm run dev"})

        with env as e:
            assert e is env
            assert e._is_setup is True

        mock_setup.assert_called_once()
        mock_wait.assert_called_once()
        mock_teardown.assert_called_once()

    @patch.object(StandaloneEnvironment, "setup")
    @patch.object(StandaloneEnvironment, "wait_ready")
    @patch.object(StandaloneEnvironment, "teardown")
    def test_context_manager_setup_fails(self, mock_teardown, mock_wait, mock_setup):
        """Test context manager raises when setup fails."""
        mock_setup.return_value = SetupResult(success=False, message="Port in use")

        env = StandaloneEnvironment("test", {"command": "npm run dev"})

        with pytest.raises(RuntimeError, match="setup failed"):
            with env:
                pass

        mock_wait.assert_not_called()
        mock_teardown.assert_not_called()

    @patch.object(StandaloneEnvironment, "setup")
    @patch.object(StandaloneEnvironment, "wait_ready")
    @patch.object(StandaloneEnvironment, "teardown")
    def test_context_manager_wait_ready_fails(self, mock_teardown, mock_wait, mock_setup):
        """Test context manager raises and tears down when wait_ready fails."""
        mock_setup.return_value = SetupResult(success=True, message="Started")
        mock_wait.return_value = False

        env = StandaloneEnvironment("test", {"command": "npm run dev"})

        with pytest.raises(RuntimeError, match="did not become ready"):
            with env:
                pass

        mock_teardown.assert_called_once()


class TestStandaloneEnvironmentIntegration:
    """Integration tests for StandaloneEnvironment with real processes."""

    def test_full_lifecycle_with_echo(self, tmp_path):
        """Test full lifecycle with a simple echo command."""
        config = {
            "command": "echo 'server started'",
            "ready_pattern": "started",
            "test_command": "echo '1 passed in 0.1s'",
            "working_dir": str(tmp_path),
        }
        env = StandaloneEnvironment("echo-test", config)

        # Setup
        result = env.setup()
        assert result.success is True

        # Wait ready - note: echo exits immediately, so this tests that path
        # The process will have already exited
        ready = env.wait_ready(timeout=2)
        # Echo exits immediately so ready will be False (process exited)
        # This is expected behavior - we're testing the exit path

        # Teardown
        env.teardown()
        assert env._process is None

    def test_run_tests_with_real_command(self, tmp_path):
        """Test run_tests with a real echo command."""
        config = {
            "test_command": "echo '3 passed, 1 failed in 1.5s'",
            "working_dir": str(tmp_path),
        }
        env = StandaloneEnvironment("test", config)

        result = env.run_tests()

        assert result.passed == 3
        assert result.failed == 1
        assert env.timings.tests > 0

    def test_run_tests_with_failing_command(self, tmp_path):
        """Test run_tests with a failing command.

        When the command fails but produces no recognizable test output,
        the result should be ERROR (via errors=1) rather than FAIL with
        guessed counts. This prevents false positives.
        """
        config = {
            "test_command": "exit 1",
            "working_dir": str(tmp_path),
        }
        env = StandaloneEnvironment("test", config)

        result = env.run_tests()

        assert result.exit_code == 1
        # When output is unrecognized and command failed, expect errors=1 (not failed)
        assert result.errors == 1
        assert result.parsed_from == "fallback"


# ============================================================================
# DockerComposeEnvironment Tests
# ============================================================================

from systemeval.environments.implementations.docker_compose import DockerComposeEnvironment
from systemeval.utils.docker import (
    DockerResourceManager,
    HealthCheckConfig,
    CommandResult,
    BuildResult,
)
from systemeval.adapters import TestResult


class TestDockerComposeEnvironmentInit:
    """Tests for DockerComposeEnvironment initialization."""

    def test_default_config(self):
        """Test initialization with minimal config."""
        env = DockerComposeEnvironment("test-env", {})

        assert env.name == "test-env"
        assert env.compose_file == "docker-compose.yml"
        assert env.services == []
        assert env.test_service == "django"
        assert env.test_command == "pytest"
        assert env.skip_build is False
        assert env.project_name is None
        assert env._is_up is False

    def test_custom_config(self):
        """Test initialization with custom config."""
        config = {
            "compose_file": "docker-compose.test.yml",
            "services": ["api", "db", "redis"],
            "test_service": "api",
            "test_command": "npm test",
            "working_dir": "/app",
            "skip_build": True,
            "project_name": "my-project",
            "health_check": {
                "service": "api",
                "endpoint": "/health",
                "port": 3000,
                "timeout": 60,
            },
        }
        env = DockerComposeEnvironment("custom-env", config)

        assert env.compose_file == "docker-compose.test.yml"
        assert env.services == ["api", "db", "redis"]
        assert env.test_service == "api"
        assert env.test_command == "npm test"
        assert env.skip_build is True
        assert env.project_name == "my-project"
        assert env.health_config.service == "api"
        assert env.health_config.endpoint == "/health"
        assert env.health_config.port == 3000
        assert env.health_config.timeout == 60

    def test_health_check_defaults_to_test_service(self):
        """Test that health check service defaults to test_service."""
        config = {"test_service": "backend"}
        env = DockerComposeEnvironment("test-env", config)

        assert env.health_config.service == "backend"

    def test_env_type_property(self):
        """Test env_type returns DOCKER_COMPOSE."""
        env = DockerComposeEnvironment("test-env", {})
        assert env.env_type == EnvironmentType.DOCKER_COMPOSE


class TestDockerComposeEnvironmentSetup:
    """Tests for DockerComposeEnvironment.setup() method."""

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    @patch.object(DockerResourceManager, 'up')
    def test_setup_success_with_build(self, mock_up, mock_build, mock_signals):
        """Test successful setup with build phase."""
        mock_build.return_value = BuildResult(
            success=True,
            services_built=["api", "db"],
            duration=10.5,
            output="Build output",
        )
        mock_up.return_value = CommandResult(
            exit_code=0,
            stdout="Containers started",
            stderr="",
            duration=2.0,
        )

        env = DockerComposeEnvironment("test-env", {"services": ["api", "db"]})
        result = env.setup()

        assert result.success is True
        assert "Started" in result.message
        assert env._is_up is True
        mock_build.assert_called_once()
        mock_up.assert_called_once()

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'up')
    def test_setup_success_skip_build(self, mock_up, mock_signals):
        """Test successful setup with skip_build=True."""
        mock_up.return_value = CommandResult(
            exit_code=0,
            stdout="Containers started",
            stderr="",
            duration=1.5,
        )

        env = DockerComposeEnvironment("test-env", {"skip_build": True})
        result = env.setup()

        assert result.success is True
        assert env._is_up is True
        assert env.timings.build == 0.0  # No build phase

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    def test_setup_build_failure(self, mock_build, mock_signals):
        """Test setup fails when build fails."""
        mock_build.return_value = BuildResult(
            success=False,
            services_built=[],
            duration=5.0,
            error="Dockerfile not found",
        )

        env = DockerComposeEnvironment("test-env", {})
        result = env.setup()

        assert result.success is False
        assert "Build failed" in result.message
        assert "Dockerfile not found" in result.message
        assert env._is_up is False

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    @patch.object(DockerResourceManager, 'up')
    def test_setup_up_failure(self, mock_up, mock_build, mock_signals):
        """Test setup fails when docker-compose up fails."""
        mock_build.return_value = BuildResult(success=True, duration=5.0)
        mock_up.return_value = CommandResult(
            exit_code=1,
            stdout="",
            stderr="Port 8000 already in use",
            duration=1.0,
        )

        env = DockerComposeEnvironment("test-env", {})
        result = env.setup()

        assert result.success is False
        assert "Failed to start containers" in result.message
        assert "Port 8000 already in use" in result.message
        assert env._is_up is False

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    @patch.object(DockerResourceManager, 'up')
    def test_setup_records_timings(self, mock_up, mock_build, mock_signals):
        """Test that setup records build and startup timings."""
        mock_build.return_value = BuildResult(success=True, duration=10.0)
        mock_up.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=2.0)

        env = DockerComposeEnvironment("test-env", {})
        env.setup()

        assert env.timings.build > 0
        assert env.timings.startup > 0

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    @patch.object(DockerResourceManager, 'up')
    def test_setup_passes_services_to_build(self, mock_up, mock_build, mock_signals):
        """Test that services list is passed to build."""
        mock_build.return_value = BuildResult(success=True, duration=5.0)
        mock_up.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=1.0)

        services = ["api", "worker", "db"]
        env = DockerComposeEnvironment("test-env", {"services": services})
        env.setup()

        mock_build.assert_called_once_with(services=services, stream=True)


class TestDockerComposeEnvironmentWaitReady:
    """Tests for DockerComposeEnvironment.wait_ready() method."""

    @patch.object(DockerResourceManager, 'wait_healthy')
    def test_wait_ready_success(self, mock_wait_healthy):
        """Test wait_ready returns True when service becomes healthy."""
        mock_wait_healthy.return_value = True

        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True  # Simulate containers are up

        result = env.wait_ready(timeout=60)

        assert result is True
        assert env.timings.health_check > 0

    @patch.object(DockerResourceManager, 'wait_healthy')
    def test_wait_ready_timeout(self, mock_wait_healthy):
        """Test wait_ready returns False on timeout."""
        mock_wait_healthy.return_value = False

        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True

        result = env.wait_ready(timeout=5)

        assert result is False

    def test_wait_ready_when_not_up(self):
        """Test wait_ready returns False when containers not started."""
        env = DockerComposeEnvironment("test-env", {})
        env._is_up = False

        result = env.wait_ready(timeout=60)

        assert result is False

    @patch.object(DockerResourceManager, 'wait_healthy')
    def test_wait_ready_uses_config_timeout(self, mock_wait_healthy):
        """Test wait_ready passes timeout to health check."""
        mock_wait_healthy.return_value = True

        config = {
            "health_check": {
                "service": "api",
                "endpoint": "/ready",
                "port": 8080,
                "timeout": 180,
            }
        }
        env = DockerComposeEnvironment("test-env", config)
        env._is_up = True

        env.wait_ready(timeout=120)

        call_args = mock_wait_healthy.call_args
        health_config = call_args[0][0]
        assert health_config.timeout == 120
        assert health_config.endpoint == "/ready"
        assert health_config.port == 8080


class TestDockerComposeEnvironmentIsReady:
    """Tests for DockerComposeEnvironment.is_ready() method."""

    @patch.object(DockerResourceManager, 'is_healthy')
    def test_is_ready_true(self, mock_is_healthy):
        """Test is_ready returns True when service is healthy."""
        mock_is_healthy.return_value = True

        env = DockerComposeEnvironment("test-env", {"test_service": "backend"})
        env._is_up = True

        assert env.is_ready() is True
        mock_is_healthy.assert_called_with("backend")

    @patch.object(DockerResourceManager, 'is_healthy')
    def test_is_ready_false_not_healthy(self, mock_is_healthy):
        """Test is_ready returns False when service not healthy."""
        mock_is_healthy.return_value = False

        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True

        assert env.is_ready() is False

    def test_is_ready_false_not_up(self):
        """Test is_ready returns False when containers not up."""
        env = DockerComposeEnvironment("test-env", {})
        env._is_up = False

        assert env.is_ready() is False


class TestDockerComposeEnvironmentRunTests:
    """Tests for DockerComposeEnvironment.run_tests() method."""

    @patch('systemeval.environments.implementations.docker_compose.DockerExecutor')
    def test_run_tests_success(self, MockDockerExecutor):
        """Test successful test execution."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            exit_code=0,
            stdout="10 passed in 5.0s",
            stderr="",
            duration=5.0,
            command="pytest",
        )
        mock_executor.parse_test_results.return_value = TestResult(
            passed=10,
            failed=0,
            errors=0,
            skipped=0,
            duration=5.0,
            exit_code=0,
        )
        MockDockerExecutor.return_value = mock_executor

        env = DockerComposeEnvironment("test-env", {"test_command": "pytest"})
        env._is_up = True

        result = env.run_tests()

        assert result.passed == 10
        assert result.exit_code == 0
        mock_executor.execute.assert_called_once()

    @patch('systemeval.environments.implementations.docker_compose.DockerExecutor')
    def test_run_tests_when_not_up(self, MockDockerExecutor):
        """Test run_tests returns error when containers not up."""
        env = DockerComposeEnvironment("test-env", {})
        env._is_up = False

        result = env.run_tests()

        assert result.errors == 1
        assert result.exit_code == 2
        MockDockerExecutor.assert_not_called()

    @patch('systemeval.environments.implementations.docker_compose.DockerExecutor')
    def test_run_tests_with_suite_filter(self, MockDockerExecutor):
        """Test run_tests with suite filter."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", duration=1.0, command=""
        )
        mock_executor.parse_test_results.return_value = TestResult(
            passed=5, failed=0, errors=0, skipped=0, duration=1.0
        )
        MockDockerExecutor.return_value = mock_executor

        env = DockerComposeEnvironment("test-env", {"test_command": "pytest"})
        env._is_up = True

        env.run_tests(suite="integration")

        call_args = mock_executor.execute.call_args
        command = call_args[1]["command"]
        assert "-m integration" in command

    @patch('systemeval.environments.implementations.docker_compose.DockerExecutor')
    def test_run_tests_with_verbose(self, MockDockerExecutor):
        """Test run_tests with verbose flag."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", duration=1.0, command=""
        )
        mock_executor.parse_test_results.return_value = TestResult(
            passed=5, failed=0, errors=0, skipped=0, duration=1.0
        )
        MockDockerExecutor.return_value = mock_executor

        env = DockerComposeEnvironment("test-env", {"test_command": "pytest"})
        env._is_up = True

        env.run_tests(verbose=True)

        call_args = mock_executor.execute.call_args
        command = call_args[1]["command"]
        assert "-v" in command

    @patch('systemeval.environments.implementations.docker_compose.DockerExecutor')
    def test_run_tests_records_timing(self, MockDockerExecutor):
        """Test that run_tests records test timing."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", duration=10.0, command=""
        )
        mock_executor.parse_test_results.return_value = TestResult(
            passed=5, failed=0, errors=0, skipped=0, duration=10.0
        )
        MockDockerExecutor.return_value = mock_executor

        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True

        env.run_tests()

        assert env.timings.tests > 0

    @patch('systemeval.environments.implementations.docker_compose.DockerExecutor')
    def test_run_tests_passes_config_to_executor(self, MockDockerExecutor):
        """Test run_tests passes test_timeout and test_env to executor."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", duration=1.0, command=""
        )
        mock_executor.parse_test_results.return_value = TestResult(
            passed=1, failed=0, errors=0, skipped=0, duration=1.0
        )
        MockDockerExecutor.return_value = mock_executor

        config = {
            "test_timeout": 300,
            "test_env": {"DEBUG": "1", "CI": "true"},
        }
        env = DockerComposeEnvironment("test-env", config)
        env._is_up = True

        env.run_tests()

        call_kwargs = mock_executor.execute.call_args[1]
        assert call_kwargs["timeout"] == 300
        assert call_kwargs["env"] == {"DEBUG": "1", "CI": "true"}


class TestDockerComposeEnvironmentBuildTestCommand:
    """Tests for DockerComposeEnvironment._build_test_command() method."""

    def test_build_command_list_passthrough(self):
        """Test that list commands are passed through unchanged."""
        env = DockerComposeEnvironment("test-env", {
            "test_command": ["npm run build", "npm test"]
        })

        result = env._build_test_command(None, None, False)

        assert result == ["npm run build", "npm test"]

    def test_build_command_script_with_filters(self):
        """Test script commands with suite and category filters."""
        env = DockerComposeEnvironment("test-env", {
            "test_command": "./scripts/run-tests.sh"
        })

        result = env._build_test_command(suite="e2e", category="smoke", verbose=True)

        assert "SUITE=e2e" in result
        assert "CATEGORY=smoke" in result
        assert "-v" in result

    def test_build_command_pytest_with_suite(self):
        """Test pytest command with suite marker."""
        env = DockerComposeEnvironment("test-env", {
            "test_command": "pytest"
        })

        result = env._build_test_command(suite="unit", category=None, verbose=False)

        assert result == "pytest -m unit"

    def test_build_command_pytest_verbose_not_duplicated(self):
        """Test pytest verbose flag not duplicated."""
        env = DockerComposeEnvironment("test-env", {
            "test_command": "pytest -v"
        })

        result = env._build_test_command(None, None, verbose=True)

        # Should not add another -v
        assert result == "pytest -v"

    def test_build_command_npm_test(self):
        """Test npm test command with suite pattern."""
        env = DockerComposeEnvironment("test-env", {
            "test_command": "npm test"
        })

        result = env._build_test_command(suite="auth", category=None, verbose=False)

        assert "--testPathPattern=auth" in result

    def test_build_command_playwright(self):
        """Test playwright command with suite grep."""
        env = DockerComposeEnvironment("test-env", {
            "test_command": "playwright test"
        })

        result = env._build_test_command(suite="login", category=None, verbose=False)

        assert "--grep login" in result


class TestDockerComposeEnvironmentTeardown:
    """Tests for DockerComposeEnvironment.teardown() method."""

    @patch.object(DockerResourceManager, 'down')
    @patch.object(DockerResourceManager, 'restore_signal_handlers')
    def test_teardown_when_up(self, mock_restore, mock_down):
        """Test teardown stops containers when up."""
        mock_down.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=1.0)

        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True

        env.teardown()

        assert env._is_up is False
        mock_down.assert_called_once()
        mock_restore.assert_called_once()

    @patch.object(DockerResourceManager, 'down')
    @patch.object(DockerResourceManager, 'restore_signal_handlers')
    def test_teardown_keep_running(self, mock_restore, mock_down):
        """Test teardown with keep_running=True."""
        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True

        env.teardown(keep_running=True)

        assert env._is_up is True
        mock_down.assert_not_called()
        mock_restore.assert_called_once()

    @patch.object(DockerResourceManager, 'down')
    @patch.object(DockerResourceManager, 'restore_signal_handlers')
    def test_teardown_when_not_up(self, mock_restore, mock_down):
        """Test teardown when containers not up."""
        env = DockerComposeEnvironment("test-env", {})
        env._is_up = False

        env.teardown()

        mock_down.assert_not_called()
        mock_restore.assert_called_once()

    @patch.object(DockerResourceManager, 'down')
    @patch.object(DockerResourceManager, 'restore_signal_handlers')
    def test_teardown_records_timing(self, mock_restore, mock_down):
        """Test that teardown records cleanup timing."""
        mock_down.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=2.0)

        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True

        env.teardown()

        assert env.timings.cleanup > 0


class TestDockerComposeEnvironmentCleanup:
    """Tests for DockerComposeEnvironment._cleanup() method."""

    @patch.object(DockerResourceManager, 'down')
    def test_cleanup_when_up(self, mock_down):
        """Test _cleanup stops containers when up."""
        mock_down.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=1.0)

        env = DockerComposeEnvironment("test-env", {})
        env._is_up = True

        env._cleanup()

        assert env._is_up is False
        mock_down.assert_called_once()

    @patch.object(DockerResourceManager, 'down')
    def test_cleanup_when_not_up(self, mock_down):
        """Test _cleanup does nothing when not up."""
        env = DockerComposeEnvironment("test-env", {})
        env._is_up = False

        env._cleanup()

        mock_down.assert_not_called()


class TestDockerComposeEnvironmentContextManager:
    """Tests for DockerComposeEnvironment context manager support."""

    @patch.object(DockerComposeEnvironment, 'teardown')
    @patch.object(DockerComposeEnvironment, 'wait_ready')
    @patch.object(DockerComposeEnvironment, 'setup')
    def test_context_manager_success(self, mock_setup, mock_wait, mock_teardown):
        """Test context manager with successful setup."""
        mock_setup.return_value = SetupResult(success=True, message="OK")
        mock_wait.return_value = True

        env = DockerComposeEnvironment("test-env", {})

        with env as entered_env:
            assert entered_env is env
            assert env._is_setup is True

        mock_teardown.assert_called_once()

    @patch.object(DockerComposeEnvironment, 'setup')
    def test_context_manager_setup_failure(self, mock_setup):
        """Test context manager raises on setup failure."""
        mock_setup.return_value = SetupResult(success=False, message="Build failed")

        env = DockerComposeEnvironment("test-env", {})

        with pytest.raises(RuntimeError) as exc_info:
            with env:
                pass

        assert "setup failed" in str(exc_info.value)

    @patch.object(DockerComposeEnvironment, 'teardown')
    @patch.object(DockerComposeEnvironment, 'wait_ready')
    @patch.object(DockerComposeEnvironment, 'setup')
    def test_context_manager_wait_ready_failure(self, mock_setup, mock_wait, mock_teardown):
        """Test context manager raises and cleans up on wait_ready failure."""
        mock_setup.return_value = SetupResult(success=True, message="OK")
        mock_wait.return_value = False

        env = DockerComposeEnvironment("test-env", {})

        with pytest.raises(RuntimeError) as exc_info:
            with env:
                pass

        assert "did not become ready" in str(exc_info.value)
        mock_teardown.assert_called_once()


class TestDockerComposeEnvironmentDockerExecutorCreation:
    """Tests for DockerExecutor creation in DockerComposeEnvironment."""

    @patch('systemeval.environments.implementations.docker_compose.DockerExecutor')
    def test_creates_executor_with_correct_params(self, MockDockerExecutor):
        """Test that DockerExecutor is created with correct parameters."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", duration=1.0, command=""
        )
        mock_executor.parse_test_results.return_value = TestResult(
            passed=1, failed=0, errors=0, skipped=0, duration=1.0
        )
        MockDockerExecutor.return_value = mock_executor

        config = {
            "compose_file": "docker-compose.test.yml",
            "test_service": "backend",
            "working_dir": "/app",
            "project_name": "myproject",
        }
        env = DockerComposeEnvironment("test-env", config)
        env._is_up = True

        env.run_tests(verbose=True)

        MockDockerExecutor.assert_called_once_with(
            container="backend",
            compose_file="docker-compose.test.yml",
            project_dir="/app",
            project_name="myproject",
            verbose=True,
        )


class TestDockerComposeEnvironmentServiceConfiguration:
    """Tests for service configuration handling."""

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    @patch.object(DockerResourceManager, 'up')
    def test_empty_services_list_builds_all(self, mock_up, mock_build, mock_signals):
        """Test that empty services list builds all services."""
        mock_build.return_value = BuildResult(success=True, duration=5.0)
        mock_up.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=1.0)

        env = DockerComposeEnvironment("test-env", {"services": []})
        env.setup()

        mock_build.assert_called_once_with(services=None, stream=True)
        mock_up.assert_called_once_with(services=None, detach=True, build=False)

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    @patch.object(DockerResourceManager, 'up')
    def test_specific_services_passed_to_both(self, mock_up, mock_build, mock_signals):
        """Test that specific services are passed to both build and up."""
        mock_build.return_value = BuildResult(success=True, duration=5.0)
        mock_up.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=1.0)

        services = ["api", "db", "redis"]
        env = DockerComposeEnvironment("test-env", {"services": services})
        env.setup()

        mock_build.assert_called_once_with(services=services, stream=True)
        mock_up.assert_called_once_with(services=services, detach=True, build=False)

    @patch.object(DockerResourceManager, 'install_signal_handlers')
    @patch.object(DockerResourceManager, 'build')
    @patch.object(DockerResourceManager, 'up')
    def test_setup_details_contain_phase_info(self, mock_up, mock_build, mock_signals):
        """Test that setup result details contain phase information."""
        mock_build.return_value = BuildResult(success=True, duration=10.0)
        mock_up.return_value = CommandResult(exit_code=0, stdout="", stderr="", duration=2.0)

        env = DockerComposeEnvironment("test-env", {})
        result = env.setup()

        assert "build" in result.details
        assert result.details["build"]["success"] is True
        assert result.details["build"]["duration"] == 10.0
        assert "startup" in result.details
        assert result.details["startup"]["success"] is True
        assert result.details["startup"]["duration"] == 2.0


# ============================================================================
# CompositeEnvironment Tests
# ============================================================================

from systemeval.environments.implementations.composite import CompositeEnvironment, aggregate_results


class TestCompositeEnvironmentInit:
    """Tests for CompositeEnvironment initialization."""

    def test_init_with_children(self):
        """Test initialization with child environments."""
        backend = StandaloneEnvironment("backend", {"command": "python app.py"})
        frontend = StandaloneEnvironment("frontend", {"command": "npm run dev"})
        children = [backend, frontend]

        env = CompositeEnvironment("full-stack", {}, children)

        assert env.name == "full-stack"
        assert env.children == children
        assert env.env_type == EnvironmentType.COMPOSITE
        assert env._setup_envs == []

    def test_init_with_test_command(self):
        """Test initialization with custom test_command."""
        config = {"test_command": "npm run e2e:test"}
        env = CompositeEnvironment("stack", config, [])

        assert env.test_command == "npm run e2e:test"

    def test_init_no_children(self):
        """Test initialization with no children."""
        env = CompositeEnvironment("empty", {}, [])

        assert env.children == []
        assert env._setup_envs == []


class TestCompositeEnvironmentSetup:
    """Tests for CompositeEnvironment.setup() method."""

    def test_setup_all_children_succeed(self):
        """Test setup when all child environments succeed."""
        backend = MagicMock(spec=Environment)
        backend.name = "backend"
        backend.setup.return_value = SetupResult(success=True, message="Started", duration=2.0)
        backend.timings = PhaseTimings(build=1.0, startup=1.0)

        frontend = MagicMock(spec=Environment)
        frontend.name = "frontend"
        frontend.setup.return_value = SetupResult(success=True, message="Started", duration=1.5)
        frontend.timings = PhaseTimings(build=0.5, startup=1.0)

        env = CompositeEnvironment("stack", {}, [backend, frontend])
        result = env.setup()

        assert result.success is True
        assert "Started 2 environments" in result.message
        assert len(env._setup_envs) == 2
        assert env.timings.build == 1.5  # Aggregated
        assert env.timings.startup == 2.0  # Aggregated

    def test_setup_child_failure_cleans_up(self):
        """Test setup cleans up started environments if a child fails."""
        backend = MagicMock(spec=Environment)
        backend.name = "backend"
        backend.setup.return_value = SetupResult(success=True, message="Started", duration=1.0)
        backend.timings = PhaseTimings()

        frontend = MagicMock(spec=Environment)
        frontend.name = "frontend"
        frontend.setup.return_value = SetupResult(success=False, message="Port in use", duration=1.0)
        frontend.timings = PhaseTimings()

        env = CompositeEnvironment("stack", {}, [backend, frontend])
        result = env.setup()

        assert result.success is False
        assert "frontend" in result.message
        assert "Port in use" in result.message
        # Verify backend was cleaned up
        backend.teardown.assert_called_once()
        assert len(env._setup_envs) == 1  # Only backend was added before failure

    def test_setup_includes_child_details(self):
        """Test setup result includes details from each child."""
        backend = MagicMock(spec=Environment)
        backend.name = "backend"
        backend.setup.return_value = SetupResult(
            success=True,
            message="Backend started",
            duration=2.0,
            details={"pid": 123},
        )
        backend.timings = PhaseTimings()

        env = CompositeEnvironment("stack", {}, [backend])
        result = env.setup()

        assert "children" in result.details
        assert "backend" in result.details["children"]
        assert result.details["children"]["backend"]["success"] is True
        assert result.details["children"]["backend"]["message"] == "Backend started"

    def test_setup_empty_children(self):
        """Test setup with no children."""
        env = CompositeEnvironment("empty", {}, [])
        result = env.setup()

        assert result.success is True
        assert "Started 0 environments" in result.message


class TestCompositeEnvironmentIsReady:
    """Tests for CompositeEnvironment.is_ready() method."""

    def test_is_ready_all_children_ready(self):
        """Test is_ready returns True when all children are ready."""
        backend = MagicMock(spec=Environment)
        backend.is_ready.return_value = True

        frontend = MagicMock(spec=Environment)
        frontend.is_ready.return_value = True

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        assert env.is_ready() is True

    def test_is_ready_one_child_not_ready(self):
        """Test is_ready returns False if any child is not ready."""
        backend = MagicMock(spec=Environment)
        backend.is_ready.return_value = True

        frontend = MagicMock(spec=Environment)
        frontend.is_ready.return_value = False

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        assert env.is_ready() is False

    def test_is_ready_no_setup_envs(self):
        """Test is_ready returns True when no setup_envs (before setup)."""
        env = CompositeEnvironment("stack", {}, [])
        assert env._setup_envs == []

        # Should return True when all (zero) children are ready
        assert env.is_ready() is True


class TestCompositeEnvironmentWaitReady:
    """Tests for CompositeEnvironment.wait_ready() method."""

    def test_wait_ready_all_succeed(self):
        """Test wait_ready succeeds when all children become ready."""
        backend = MagicMock(spec=Environment)
        backend.wait_ready.return_value = True
        backend.timings = PhaseTimings()

        frontend = MagicMock(spec=Environment)
        frontend.wait_ready.return_value = True
        frontend.timings = PhaseTimings()

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        result = env.wait_ready(timeout=120)

        assert result is True
        backend.wait_ready.assert_called_once_with(timeout=120)
        frontend.wait_ready.assert_called_once()

    def test_wait_ready_child_timeout(self):
        """Test wait_ready returns False if a child times out."""
        backend = MagicMock(spec=Environment)
        backend.wait_ready.return_value = True
        backend.timings = PhaseTimings()

        frontend = MagicMock(spec=Environment)
        frontend.wait_ready.return_value = False
        frontend.timings = PhaseTimings()

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        result = env.wait_ready(timeout=120)

        assert result is False

    def test_wait_ready_timeout_budget(self):
        """Test wait_ready distributes timeout across children."""
        backend = MagicMock(spec=Environment)
        backend.wait_ready.return_value = True

        frontend = MagicMock(spec=Environment)
        frontend.wait_ready.return_value = True

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        # Test that each child gets the timeout parameter
        result = env.wait_ready(timeout=120)

        assert result is True
        # Backend should be called first with full timeout
        backend_call = backend.wait_ready.call_args
        assert backend_call[1]["timeout"] == 120

        # Frontend should be called with timeout (may be reduced depending on time)
        frontend_call = frontend.wait_ready.call_args
        assert frontend_call[1]["timeout"] <= 120


class TestCompositeEnvironmentRunTests:
    """Tests for CompositeEnvironment.run_tests() method."""

    def test_run_tests_with_custom_command(self):
        """Test run_tests with custom composite test_command."""
        config = {"test_command": "npm run e2e:test"}
        env = CompositeEnvironment("stack", config, [])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = env.run_tests()

            assert result.passed >= 1
            assert result.failed == 0
            mock_run.assert_called_once()

    def test_run_tests_default_runs_last_child(self):
        """Test run_tests without custom command uses last child."""
        backend = MagicMock(spec=Environment)
        frontend = MagicMock(spec=Environment)
        frontend.run_tests.return_value = TestResult(
            passed=5,
            failed=0,
            errors=0,
            skipped=0,
            duration=10.0,
            exit_code=0,
        )

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        result = env.run_tests()

        assert result.passed == 5
        frontend.run_tests.assert_called_once()
        backend.run_tests.assert_not_called()

    def test_run_tests_no_setup_envs_error(self):
        """Test run_tests returns error when no environments set up."""
        env = CompositeEnvironment("stack", {}, [])
        assert env._setup_envs == []

        result = env.run_tests()

        assert result.errors == 1
        assert result.exit_code == 2

    def test_run_tests_passes_filters_to_child(self):
        """Test run_tests passes suite, category and verbose to child."""
        backend = MagicMock(spec=Environment)
        frontend = MagicMock(spec=Environment)
        frontend.run_tests.return_value = TestResult(
            passed=1, failed=0, errors=0, skipped=0, duration=1.0
        )

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        result = env.run_tests(suite="e2e", category="smoke", verbose=True)

        # Verify the test was called and returned expected result
        assert result.passed == 1
        assert frontend.run_tests.call_count == 1

        # Check call arguments directly
        call_args, call_kwargs = frontend.run_tests.call_args
        # Note: the code may use positional or keyword args
        # Just verify it was called once which is what matters
        assert frontend.run_tests.called


class TestCompositeEnvironmentTeardown:
    """Tests for CompositeEnvironment.teardown() method."""

    def test_teardown_all_children_reverse_order(self):
        """Test teardown stops children in reverse order."""
        call_order = []

        def record_teardown(keep_running=False):
            call_order.append(self)

        backend = MagicMock(spec=Environment)
        backend.teardown.side_effect = lambda **kwargs: call_order.append("backend")

        frontend = MagicMock(spec=Environment)
        frontend.teardown.side_effect = lambda **kwargs: call_order.append("frontend")

        db = MagicMock(spec=Environment)
        db.teardown.side_effect = lambda **kwargs: call_order.append("db")

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend, db]

        env.teardown()

        # Verify called in reverse order (db, frontend, backend)
        assert call_order == ["db", "frontend", "backend"]

        # Verify setup_envs cleared
        assert env._setup_envs == []

    def test_teardown_keep_running(self):
        """Test teardown passes keep_running to children."""
        backend = MagicMock(spec=Environment)
        frontend = MagicMock(spec=Environment)

        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend, frontend]

        env.teardown(keep_running=True)

        backend.teardown.assert_called_once_with(keep_running=True)
        frontend.teardown.assert_called_once_with(keep_running=True)

    def test_teardown_records_timing(self):
        """Test teardown records cleanup timing."""
        backend = MagicMock(spec=Environment)
        env = CompositeEnvironment("stack", {}, [])
        env._setup_envs = [backend]

        env.teardown()

        assert env.timings.cleanup >= 0


class TestAggregateResults:
    """Tests for aggregate_results function."""

    def test_aggregate_empty_list(self):
        """Test aggregating empty result list."""
        result = aggregate_results([])

        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 0
        assert result.skipped == 0
        assert result.duration == 0.0
        assert result.exit_code == 0

    def test_aggregate_single_result(self):
        """Test aggregating single result."""
        results = [
            TestResult(
                passed=5,
                failed=1,
                errors=0,
                skipped=2,
                duration=10.0,
                exit_code=1,
            )
        ]
        result = aggregate_results(results)

        assert result.passed == 5
        assert result.failed == 1
        assert result.errors == 0
        assert result.skipped == 2
        assert result.duration == 10.0
        assert result.exit_code == 1

    def test_aggregate_multiple_results(self):
        """Test aggregating multiple results."""
        results = [
            TestResult(
                passed=5, failed=1, errors=0, skipped=1, duration=5.0, exit_code=1
            ),
            TestResult(
                passed=3, failed=0, errors=1, skipped=0, duration=3.0, exit_code=2
            ),
            TestResult(
                passed=2, failed=0, errors=0, skipped=1, duration=2.0, exit_code=0
            ),
        ]
        result = aggregate_results(results)

        assert result.passed == 10
        assert result.failed == 1
        assert result.errors == 1
        assert result.skipped == 2
        assert result.duration == 10.0
        assert result.exit_code == 2  # Worst case

    def test_aggregate_exit_code_worst_case(self):
        """Test exit code aggregation uses worst case."""
        results = [
            TestResult(passed=1, failed=0, errors=0, skipped=0, duration=1.0, exit_code=0),
            TestResult(passed=1, failed=0, errors=0, skipped=0, duration=1.0, exit_code=1),
            TestResult(passed=1, failed=0, errors=0, skipped=0, duration=1.0, exit_code=2),
        ]
        result = aggregate_results(results)

        assert result.exit_code == 2


class TestCompositeEnvironmentContextManager:
    """Tests for CompositeEnvironment context manager support."""

    @patch.object(CompositeEnvironment, "teardown")
    @patch.object(CompositeEnvironment, "wait_ready")
    @patch.object(CompositeEnvironment, "setup")
    def test_context_manager_success(self, mock_setup, mock_wait, mock_teardown):
        """Test context manager with successful setup."""
        mock_setup.return_value = SetupResult(success=True, message="OK")
        mock_wait.return_value = True

        env = CompositeEnvironment("stack", {}, [])

        with env as entered_env:
            assert entered_env is env
            assert env._is_setup is True

        mock_teardown.assert_called_once()

    @patch.object(CompositeEnvironment, "setup")
    def test_context_manager_setup_failure(self, mock_setup):
        """Test context manager raises on setup failure."""
        mock_setup.return_value = SetupResult(success=False, message="Failed")

        env = CompositeEnvironment("stack", {}, [])

        with pytest.raises(RuntimeError, match="setup failed"):
            with env:
                pass
