"""Tests for PlaywrightAdapter."""

import pytest
import json
from unittest.mock import MagicMock, patch
import subprocess

from systemeval.adapters import PlaywrightAdapter
from systemeval.adapters import TestResult, TestFailure


class TestPlaywrightAdapterInit:
    """Tests for PlaywrightAdapter initialization."""

    def test_init_with_defaults(self, tmp_path):
        """Test initialization with default values."""
        adapter = PlaywrightAdapter(str(tmp_path))
        assert adapter.config_file == "playwright.config.ts"
        assert adapter.playwright_project is None
        assert not adapter.headed
        assert adapter.timeout == 30000

    def test_init_with_custom_config(self, tmp_path):
        """Test initialization with custom configuration."""
        adapter = PlaywrightAdapter(
            str(tmp_path),
            config_file="e2e.config.ts",
            project="chromium",
            headed=True,
            timeout=60000,
        )
        assert adapter.config_file == "e2e.config.ts"
        assert adapter.playwright_project == "chromium"
        assert adapter.headed
        assert adapter.timeout == 60000


class TestPlaywrightAdapterValidateEnvironment:
    """Tests for PlaywrightAdapter validate_environment."""

    def test_validate_fails_if_npx_not_found(self, tmp_path):
        """Test validation fails if npx is not available."""
        adapter = PlaywrightAdapter(str(tmp_path))

        with patch("shutil.which", return_value=None):
            result = adapter.validate_environment()

        assert not result

    def test_validate_fails_if_no_config(self, tmp_path):
        """Test validation fails if playwright config doesn't exist."""
        adapter = PlaywrightAdapter(str(tmp_path))

        with patch("shutil.which", return_value="/usr/bin/npx"):
            result = adapter.validate_environment()

        assert not result

    def test_validate_succeeds_with_ts_config(self, tmp_path):
        """Test validation succeeds with playwright.config.ts."""
        (tmp_path / "playwright.config.ts").touch()
        adapter = PlaywrightAdapter(str(tmp_path))

        with patch("shutil.which", return_value="/usr/bin/npx"):
            result = adapter.validate_environment()

        assert result

    def test_validate_finds_alternative_js_config(self, tmp_path):
        """Test validation finds playwright.config.js as alternative."""
        (tmp_path / "playwright.config.js").touch()
        adapter = PlaywrightAdapter(str(tmp_path))

        with patch("shutil.which", return_value="/usr/bin/npx"):
            result = adapter.validate_environment()

        assert result
        assert adapter.config_file == "playwright.config.js"


class TestPlaywrightAdapterDiscover:
    """Tests for PlaywrightAdapter discover."""

    def test_discover_parses_json_output(self, tmp_path):
        """Test discover parses JSON test list output."""
        adapter = PlaywrightAdapter(str(tmp_path))

        json_output = {
            "suites": [
                {
                    "title": "Login Tests",
                    "specs": [
                        {
                            "id": "test-1",
                            "title": "should login successfully",
                            "file": "tests/login.spec.ts",
                            "line": 10,
                        }
                    ],
                    "suites": [],
                }
            ]
        }

        mock_result = MagicMock()
        mock_result.stdout = json.dumps(json_output)
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result):
                tests = adapter.discover()

        assert len(tests) == 1
        assert tests[0].name == "should login successfully"
        assert tests[0].path == "tests/login.spec.ts"
        assert "browser" in tests[0].markers

    def test_discover_handles_nested_suites(self, tmp_path):
        """Test discover handles nested test suites."""
        adapter = PlaywrightAdapter(str(tmp_path))

        json_output = {
            "suites": [
                {
                    "title": "Auth",
                    "specs": [],
                    "suites": [
                        {
                            "title": "Login",
                            "specs": [
                                {"id": "test-1", "title": "succeeds", "file": "auth.spec.ts"},
                                {"id": "test-2", "title": "fails on wrong password", "file": "auth.spec.ts"},
                            ],
                            "suites": [],
                        }
                    ],
                }
            ]
        }

        mock_result = MagicMock()
        mock_result.stdout = json.dumps(json_output)
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result):
                tests = adapter.discover()

        assert len(tests) == 2

    def test_discover_handles_timeout(self, tmp_path):
        """Test discover handles subprocess timeout gracefully."""
        adapter = PlaywrightAdapter(str(tmp_path))

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 60)):
                tests = adapter.discover()

        assert tests == []


class TestPlaywrightAdapterExecute:
    """Tests for PlaywrightAdapter execute."""

    def test_execute_parses_success_result(self, tmp_path):
        """Test execute parses successful test run."""
        adapter = PlaywrightAdapter(str(tmp_path))

        json_output = {
            "stats": {
                "expected": 5,
                "unexpected": 0,
                "skipped": 1,
                "flaky": 0,
            },
            "suites": [],
        }

        mock_result = MagicMock()
        mock_result.stdout = json.dumps(json_output)
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result):
                result = adapter.execute()

        assert result.passed == 5
        assert result.failed == 0
        assert result.skipped == 1
        assert result.exit_code == 0
        assert result.parsed_from == "playwright"

    def test_execute_parses_failure_result(self, tmp_path):
        """Test execute parses test failure details."""
        adapter = PlaywrightAdapter(str(tmp_path))

        json_output = {
            "stats": {
                "expected": 3,
                "unexpected": 2,
                "skipped": 0,
                "flaky": 0,
            },
            "suites": [
                {
                    "title": "Tests",
                    "specs": [
                        {
                            "id": "test-1",
                            "title": "should fail",
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "failed",
                                            "duration": 1500,
                                            "error": {
                                                "message": "Expected true to be false",
                                                "stack": "at test.spec.ts:10",
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                    "suites": [],
                }
            ],
        }

        mock_result = MagicMock()
        mock_result.stdout = json.dumps(json_output)
        mock_result.stderr = ""
        mock_result.returncode = 1

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result):
                result = adapter.execute()

        assert result.passed == 3
        assert result.failed == 2
        assert result.exit_code == 1
        assert len(result.failures) == 1
        assert result.failures[0].message == "Expected true to be false"

    def test_execute_handles_timeout(self, tmp_path):
        """Test execute handles subprocess timeout."""
        adapter = PlaywrightAdapter(str(tmp_path))

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
                result = adapter.execute()

        assert result.errors == 1
        assert result.exit_code == 2
        assert "timed out" in result.failures[0].message.lower()

    def test_execute_handles_invalid_json(self, tmp_path):
        """Test execute handles non-JSON output gracefully."""
        adapter = PlaywrightAdapter(str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = "Not valid JSON output"
        mock_result.stderr = "Test failed"
        mock_result.returncode = 1

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result):
                result = adapter.execute()

        assert result.failed == 1
        assert result.parsed_from == "fallback"
        assert result.parsing_warning is not None

    def test_execute_passes_parallel_flag(self, tmp_path):
        """Test execute passes parallel worker configuration."""
        adapter = PlaywrightAdapter(str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = '{"stats": {"expected": 1}}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result) as run_mock:
                adapter.execute(parallel=True)

        cmd = run_mock.call_args[0][0]
        assert "--workers" in cmd
        workers_idx = cmd.index("--workers")
        assert cmd[workers_idx + 1] == "auto"

    def test_execute_passes_failfast_flag(self, tmp_path):
        """Test execute passes max-failures flag for failfast."""
        adapter = PlaywrightAdapter(str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = '{"stats": {"expected": 1}}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result) as run_mock:
                adapter.execute(failfast=True)

        cmd = run_mock.call_args[0][0]
        assert "--max-failures=1" in cmd


class TestPlaywrightAdapterGetMarkers:
    """Tests for PlaywrightAdapter get_available_markers."""

    def test_get_available_markers(self, tmp_path):
        """Test get_available_markers returns expected list."""
        adapter = PlaywrightAdapter(str(tmp_path))
        markers = adapter.get_available_markers()

        assert "browser" in markers
        assert "e2e" in markers
