"""Tests for the Vitest adapter."""

import json
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from systemeval.adapters import VitestAdapter
from systemeval.types import AdapterConfig, TestItem


class TestVitestAdapterInit:
    """Tests for VitestAdapter initialization."""

    def test_init_with_project_root_string(self, tmp_path: Path):
        """Test initialization with project root string."""
        adapter = VitestAdapter(str(tmp_path))
        assert adapter.project_root == str(tmp_path)
        assert adapter.config_file == "vitest.config.ts"

    def test_init_with_adapter_config(self, tmp_path: Path):
        """Test initialization with AdapterConfig."""
        config = AdapterConfig(
            project_root=str(tmp_path),
            timeout=120,
            extra={
                "config_file": "vitest.config.js",
            }
        )
        adapter = VitestAdapter(config)
        assert adapter.project_root == str(tmp_path)
        assert adapter.config_file == "vitest.config.js"
        assert adapter.timeout == 120

    def test_init_with_custom_config_file(self, tmp_path: Path):
        """Test initialization with custom config file."""
        adapter = VitestAdapter(str(tmp_path), config_file="custom.vitest.config.ts")
        assert adapter.config_file == "custom.vitest.config.ts"


class TestVitestAdapterBuildCommand:
    """Tests for command building."""

    def test_build_base_command(self, tmp_path: Path):
        """Test building base vitest command."""
        adapter = VitestAdapter(str(tmp_path))
        with patch.object(adapter, '_get_npx_path', return_value='/usr/bin/npx'):
            cmd = adapter._build_base_command()
            assert cmd[0] == '/usr/bin/npx'
            assert cmd[1] == 'vitest'
            assert cmd[2] == 'run'

    def test_build_command_with_config(self, tmp_path: Path):
        """Test command includes config file when it exists."""
        config_file = tmp_path / "vitest.config.ts"
        config_file.write_text("export default {}")

        adapter = VitestAdapter(str(tmp_path))
        with patch.object(adapter, '_get_npx_path', return_value='/usr/bin/npx'):
            cmd = adapter._build_base_command()
            assert '--config' in cmd
            assert str(config_file) in cmd


class TestVitestAdapterGetCommand:
    """Tests for get_command method."""

    def test_get_command_basic(self, tmp_path: Path):
        """Test get_command returns expected command."""
        adapter = VitestAdapter(str(tmp_path))
        with patch.object(adapter, '_get_npx_path', return_value='/usr/bin/npx'):
            cmd = adapter.get_command()
            assert '/usr/bin/npx' in cmd
            assert 'vitest' in cmd
            assert 'run' in cmd
            assert '--reporter=json' in cmd

    def test_get_command_with_coverage(self, tmp_path: Path):
        """Test get_command with coverage enabled."""
        adapter = VitestAdapter(str(tmp_path))
        with patch.object(adapter, '_get_npx_path', return_value='/usr/bin/npx'):
            cmd = adapter.get_command(coverage=True)
            assert '--coverage' in cmd

    def test_get_command_with_failfast(self, tmp_path: Path):
        """Test get_command with failfast enabled."""
        adapter = VitestAdapter(str(tmp_path))
        with patch.object(adapter, '_get_npx_path', return_value='/usr/bin/npx'):
            cmd = adapter.get_command(failfast=True)
            assert '--bail' in cmd

    def test_get_command_without_parallel(self, tmp_path: Path):
        """Test get_command with parallel disabled."""
        adapter = VitestAdapter(str(tmp_path))
        with patch.object(adapter, '_get_npx_path', return_value='/usr/bin/npx'):
            cmd = adapter.get_command(parallel=False)
            assert '--no-threads' in cmd

    def test_get_command_with_parallel(self, tmp_path: Path):
        """Test get_command with parallel enabled (no --no-threads)."""
        adapter = VitestAdapter(str(tmp_path))
        with patch.object(adapter, '_get_npx_path', return_value='/usr/bin/npx'):
            cmd = adapter.get_command(parallel=True)
            assert '--no-threads' not in cmd


class TestVitestAdapterParseResults:
    """Tests for result parsing."""

    def test_parse_passing_results(self, tmp_path: Path):
        """Test parsing successful test results."""
        adapter = VitestAdapter(str(tmp_path))

        json_output = json.dumps({
            "numTotalTestSuites": 2,
            "numPassedTestSuites": 2,
            "numFailedTestSuites": 0,
            "numTotalTests": 10,
            "numPassedTests": 10,
            "numFailedTests": 0,
            "numPendingTests": 0,
            "numTodoTests": 0,
            "success": True,
            "testResults": []
        })

        result = adapter._parse_results(json_output, "", 0, 1.5)

        assert result.passed == 10
        assert result.failed == 0
        assert result.skipped == 0
        assert result.exit_code == 0
        assert result.parsed_from == "vitest"

    def test_parse_failing_results(self, tmp_path: Path):
        """Test parsing failed test results."""
        adapter = VitestAdapter(str(tmp_path))

        json_output = json.dumps({
            "numTotalTestSuites": 2,
            "numPassedTestSuites": 1,
            "numFailedTestSuites": 1,
            "numTotalTests": 10,
            "numPassedTests": 9,
            "numFailedTests": 1,
            "numPendingTests": 0,
            "numTodoTests": 0,
            "success": False,
            "testResults": [
                {
                    "name": "/path/to/test.spec.ts",
                    "status": "failed",
                    "assertionResults": [
                        {
                            "ancestorTitles": ["describe"],
                            "fullName": "describe test name",
                            "status": "failed",
                            "title": "test name",
                            "duration": 10,
                            "failureMessages": ["Expected true to be false"]
                        }
                    ]
                }
            ]
        })

        result = adapter._parse_results(json_output, "", 1, 2.0)

        assert result.passed == 9
        assert result.failed == 1
        assert result.exit_code == 1
        assert len(result.failures) == 1
        assert result.failures[0].test_name == "test name"
        assert "Expected true to be false" in result.failures[0].message

    def test_parse_skipped_tests(self, tmp_path: Path):
        """Test parsing results with skipped/pending tests."""
        adapter = VitestAdapter(str(tmp_path))

        json_output = json.dumps({
            "numTotalTests": 15,
            "numPassedTests": 10,
            "numFailedTests": 0,
            "numPendingTests": 3,
            "numTodoTests": 2,
            "success": True,
            "testResults": []
        })

        result = adapter._parse_results(json_output, "", 0, 1.0)

        assert result.passed == 10
        assert result.failed == 0
        assert result.skipped == 5  # pending + todo
        assert result.exit_code == 0

    def test_parse_invalid_json_fallback(self, tmp_path: Path):
        """Test fallback when JSON parsing fails."""
        adapter = VitestAdapter(str(tmp_path))

        result = adapter._parse_results("not valid json", "Error message", 1, 1.0)

        assert result.passed == 0
        assert result.failed == 1
        assert result.exit_code == 1
        assert result.parsed_from == "fallback"
        assert result.parsing_warning is not None

    def test_parse_invalid_json_success_exit(self, tmp_path: Path):
        """Test fallback with exit code 0 assumes pass."""
        adapter = VitestAdapter(str(tmp_path))

        result = adapter._parse_results("not valid json", "", 0, 1.0)

        assert result.passed == 1
        assert result.failed == 0


class TestVitestAdapterValidateEnvironment:
    """Tests for environment validation."""

    def test_validate_environment_no_npx(self, tmp_path: Path):
        """Test validation fails when npx not found."""
        adapter = VitestAdapter(str(tmp_path))
        with patch('shutil.which', return_value=None):
            assert adapter.validate_environment() is False

    def test_validate_environment_with_config(self, tmp_path: Path):
        """Test validation passes with config file."""
        config_file = tmp_path / "vitest.config.ts"
        config_file.write_text("export default {}")

        adapter = VitestAdapter(str(tmp_path))
        with patch('shutil.which', return_value='/usr/bin/npx'):
            assert adapter.validate_environment() is True

    def test_validate_environment_finds_alternative_config(self, tmp_path: Path):
        """Test validation finds alternative config files."""
        config_file = tmp_path / "vite.config.ts"
        config_file.write_text("export default {}")

        adapter = VitestAdapter(str(tmp_path))
        with patch('shutil.which', return_value='/usr/bin/npx'):
            assert adapter.validate_environment() is True
            assert adapter.config_file == "vite.config.ts"

    def test_validate_environment_no_config_still_passes(self, tmp_path: Path):
        """Test validation passes even without config (Vitest default)."""
        adapter = VitestAdapter(str(tmp_path))
        with patch('shutil.which', return_value='/usr/bin/npx'):
            # Vitest can work without explicit config
            assert adapter.validate_environment() is True


class TestVitestAdapterGetAvailableMarkers:
    """Tests for available markers."""

    def test_get_available_markers(self, tmp_path: Path):
        """Test get_available_markers returns expected markers."""
        adapter = VitestAdapter(str(tmp_path))
        markers = adapter.get_available_markers()

        assert "vitest" in markers
        assert "unit" in markers
        assert "integration" in markers
        assert "component" in markers


class TestVitestAdapterDiscover:
    """Tests for test discovery."""

    def test_discover_parses_json_output(self, tmp_path: Path):
        """Test discover parses JSON output correctly."""
        adapter = VitestAdapter(str(tmp_path))

        json_output = json.dumps({
            "testResults": [
                {
                    "name": "/path/to/math.test.ts",
                    "assertionResults": [
                        {
                            "ancestorTitles": ["Math"],
                            "fullName": "Math adds numbers",
                            "status": "passed",
                            "title": "adds numbers",
                            "duration": 5
                        },
                        {
                            "ancestorTitles": ["Math"],
                            "fullName": "Math subtracts numbers",
                            "status": "passed",
                            "title": "subtracts numbers",
                            "duration": 3
                        }
                    ]
                }
            ]
        })

        mock_result = MagicMock()
        mock_result.stdout = json_output
        mock_result.returncode = 0

        with patch('subprocess.run', return_value=mock_result):
            with patch('shutil.which', return_value='/usr/bin/npx'):
                tests = adapter.discover()

        assert len(tests) == 2
        assert tests[0].name == "adds numbers"
        assert tests[0].path == "/path/to/math.test.ts"
        assert tests[0].suite == "Math"


class TestVitestAdapterExecute:
    """Tests for test execution."""

    def test_execute_returns_test_result(self, tmp_path: Path):
        """Test execute returns TestResult."""
        adapter = VitestAdapter(str(tmp_path))

        json_output = json.dumps({
            "numTotalTests": 5,
            "numPassedTests": 5,
            "numFailedTests": 0,
            "numPendingTests": 0,
            "numTodoTests": 0,
            "success": True,
            "testResults": []
        })

        mock_result = MagicMock()
        mock_result.stdout = json_output
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch('subprocess.run', return_value=mock_result):
            with patch('shutil.which', return_value='/usr/bin/npx'):
                result = adapter.execute()

        assert result.passed == 5
        assert result.failed == 0
        assert result.exit_code == 0

    def test_execute_handles_timeout(self, tmp_path: Path):
        """Test execute handles timeout gracefully."""
        import subprocess
        adapter = VitestAdapter(str(tmp_path), timeout=1)

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 1)):
            with patch('shutil.which', return_value='/usr/bin/npx'):
                result = adapter.execute()

        assert result.errors == 1
        assert result.exit_code == 2
        assert len(result.failures) == 1
        assert "timed out" in result.failures[0].message

    def test_execute_handles_missing_npx(self, tmp_path: Path):
        """Test execute handles missing npx gracefully."""
        adapter = VitestAdapter(str(tmp_path))

        with patch('subprocess.run', side_effect=FileNotFoundError()):
            with patch('shutil.which', return_value='/usr/bin/npx'):
                result = adapter.execute()

        assert result.errors == 1
        assert result.exit_code == 2
        assert "not found" in result.failures[0].message


class TestVitestAdapterIntegration:
    """Integration tests for VitestAdapter with AdapterConfig."""

    def test_adapter_config_extra_settings(self, tmp_path: Path):
        """Test adapter respects extra settings from AdapterConfig."""
        config = AdapterConfig(
            project_root=str(tmp_path),
            timeout=180,
            coverage=True,
            parallel=True,
            extra={
                "config_file": "custom.vitest.config.ts",
            }
        )

        adapter = VitestAdapter(config)

        assert adapter.config_file == "custom.vitest.config.ts"
        assert adapter.timeout == 180

    def test_adapter_registered_in_registry(self):
        """Test VitestAdapter is registered in the global registry."""
        from systemeval.adapters import list_adapters

        adapters = list_adapters()
        assert "vitest" in adapters

    def test_adapter_can_be_retrieved_from_registry(self, tmp_path: Path):
        """Test VitestAdapter can be retrieved from registry."""
        from systemeval.adapters import get_adapter

        adapter = get_adapter("vitest", str(tmp_path))
        assert isinstance(adapter, VitestAdapter)
