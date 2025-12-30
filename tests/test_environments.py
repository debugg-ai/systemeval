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
        """Test parsing unknown format with failure exit code."""
        executor = TestExecutor()
        output = "Something went wrong"

        result = executor.parse_test_results(output, exit_code=1)

        # Should assume at least 1 failed
        assert result.failed >= 1
        assert result.exit_code == 1

    def test_parse_with_skipped(self):
        """Test parsing output with skipped tests."""
        executor = TestExecutor()
        output = "10 passed, 3 skipped in 5.0s"

        result = executor.parse_test_results(output, exit_code=0)

        assert result.passed == 10
        assert result.skipped == 3


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
