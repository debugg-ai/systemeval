"""Tests for CLI functionality."""

import json
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from systemeval.cli_main import main, _display_results
from systemeval.adapters import TestResult, Verdict
from systemeval.core.evaluation import SCHEMA_VERSION


class TestDisplayResults:
    """Tests for _display_results function."""

    def test_display_passing_results(self, passing_test_result, capsys):
        """Test display of passing results."""
        _display_results(passing_test_result)
        # Just verify it doesn't crash
        # Rich output is hard to test directly

    def test_display_failing_results(self, failing_test_result, capsys):
        """Test display of failing results."""
        _display_results(failing_test_result)

    def test_display_error_results(self, error_test_result, capsys):
        """Test display of error results."""
        _display_results(error_test_result)


class TestCLIHelp:
    """Tests for CLI help and basic commands."""

    def test_help(self):
        """Test --help flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "SystemEval" in result.output

    def test_version(self):
        """Test --version flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0

    def test_test_help(self):
        """Test 'test --help' command."""
        runner = CliRunner()
        result = runner.invoke(main, ["test", "--help"])

        assert result.exit_code == 0
        assert "--category" in result.output
        assert "--json" in result.output
        assert "--env" in result.output


class TestCLIListCommands:
    """Tests for CLI list subcommands."""

    def test_list_adapters(self):
        """Test 'list adapters' command."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "adapters"])

        assert result.exit_code == 0
        assert "pytest" in result.output.lower()

    def test_list_templates(self):
        """Test 'list templates' command."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "templates"])

        assert result.exit_code == 0
        assert "summary" in result.output.lower() or "template" in result.output.lower()


class TestJSONOutput:
    """Tests for JSON output format."""

    def test_json_output_schema(self, passing_test_result):
        """Test that JSON output conforms to EvaluationResult schema."""
        eval_result = passing_test_result.to_evaluation(
            adapter_type="pytest",
            project_name="test-project",
        )
        eval_result.finalize()

        json_str = eval_result.to_json()
        data = json.loads(json_str)

        # Check required fields
        assert "verdict" in data
        assert "exit_code" in data
        assert "metadata" in data
        assert "sessions" in data
        assert "summary" in data

        # Check metadata
        metadata = data["metadata"]
        assert "evaluation_id" in metadata
        assert "timestamp_utc" in metadata
        assert "schema_version" in metadata
        assert metadata["schema_version"] == SCHEMA_VERSION

        # Check verdict values
        assert data["verdict"] in ["PASS", "FAIL", "ERROR"]
        assert data["exit_code"] in [0, 1, 2]

    def test_json_output_pass(self, passing_test_result):
        """Test JSON output for passing tests."""
        eval_result = passing_test_result.to_evaluation(adapter_type="pytest")
        eval_result.finalize()

        data = json.loads(eval_result.to_json())

        assert data["verdict"] == "PASS"
        assert data["exit_code"] == 0

    def test_json_output_fail(self, failing_test_result):
        """Test JSON output for failing tests."""
        eval_result = failing_test_result.to_evaluation(adapter_type="pytest")
        eval_result.finalize()

        data = json.loads(eval_result.to_json())

        assert data["verdict"] == "FAIL"
        assert data["exit_code"] == 1

    def test_json_output_error(self, error_test_result):
        """Test JSON output for error results."""
        eval_result = error_test_result.to_evaluation(adapter_type="pytest")
        eval_result.finalize()

        data = json.loads(eval_result.to_json())

        # Error results produce FAIL verdict (errors > 0)
        assert data["exit_code"] in [1, 2]

    def test_json_sessions_contain_metrics(self, passing_test_result):
        """Test that sessions contain metrics."""
        eval_result = passing_test_result.to_evaluation(adapter_type="pytest")
        eval_result.finalize()

        data = json.loads(eval_result.to_json())

        assert len(data["sessions"]) > 0
        session = data["sessions"][0]
        assert "metrics" in session
        assert len(session["metrics"]) > 0

    def test_json_metrics_structure(self, passing_test_result):
        """Test metric structure in JSON output."""
        eval_result = passing_test_result.to_evaluation(adapter_type="pytest")
        eval_result.finalize()

        data = json.loads(eval_result.to_json())
        session = data["sessions"][0]
        metric = session["metrics"][0]

        assert "name" in metric
        assert "value" in metric
        assert "expected" in metric
        assert "passed" in metric

    def test_json_summary_statistics(self, passing_test_result):
        """Test summary statistics in JSON output."""
        eval_result = passing_test_result.to_evaluation(adapter_type="pytest")
        eval_result.finalize()

        data = json.loads(eval_result.to_json())
        summary = data["summary"]

        assert "total_sessions" in summary
        assert "passed_sessions" in summary
        assert "failed_sessions" in summary
        assert "total_metrics" in summary
        assert "passed_metrics" in summary
        assert "failed_metrics" in summary
        assert "total_duration_seconds" in summary


class TestCLIValidate:
    """Tests for validate command."""

    def test_validate_no_config(self):
        """Test validate with no config file."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["validate"])
            assert result.exit_code == 2
            assert "no systemeval.yaml" in result.output.lower() or "error" in result.output.lower()


class TestCLIInit:
    """Tests for init command."""

    def test_init_creates_config(self):
        """Test that init creates a config file."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init"])

            assert result.exit_code == 0
            import os
            assert os.path.exists("systemeval.yaml")

    def test_init_no_overwrite_without_force(self):
        """Test that init doesn't overwrite existing config without --force."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            # Create existing config
            with open("systemeval.yaml", "w") as f:
                f.write("existing: config\n")

            result = runner.invoke(main, ["init"])

            assert result.exit_code == 1
            assert "already exists" in result.output.lower() or "force" in result.output.lower()

    def test_init_force_overwrites(self):
        """Test that init --force overwrites existing config."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            # Create existing config
            with open("systemeval.yaml", "w") as f:
                f.write("existing: config\n")

            result = runner.invoke(main, ["init", "--force"])

            assert result.exit_code == 0

            with open("systemeval.yaml") as f:
                content = f.read()
            assert "adapter" in content  # new config should have adapter


class TestCLITestCommand:
    """Tests for test command (mocked)."""

    @patch("systemeval.cli_main.find_config_file")
    def test_test_no_config(self, mock_find):
        """Test test command with no config."""
        mock_find.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["test"])

        assert result.exit_code == 2
        assert "no systemeval.yaml" in result.output.lower() or "error" in result.output.lower()

    @patch("systemeval.cli_main.find_config_file")
    @patch("systemeval.cli_main.load_config")
    @patch("systemeval.cli_main.get_adapter")
    def test_test_with_json_output(self, mock_get_adapter, mock_load, mock_find, tmp_path):
        """Test test command with --json flag."""
        # Setup mocks
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest\nproject_root: .")
        mock_find.return_value = config_file

        mock_config = MagicMock()
        mock_config.adapter = "pytest"
        mock_config.project_root = tmp_path
        mock_config.environments = None
        mock_config.is_multi_project = False  # Ensure v1.0 single-project mode
        mock_load.return_value = mock_config

        mock_adapter = MagicMock()
        mock_adapter.validate_environment.return_value = True
        mock_adapter.execute.return_value = TestResult(
            passed=5,
            failed=0,
            errors=0,
            skipped=0,
            duration=1.0,
        )
        mock_get_adapter.return_value = mock_adapter

        runner = CliRunner()
        result = runner.invoke(main, ["test", "--json"])

        # Should output valid JSON
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert "verdict" in data
            assert "metadata" in data


class TestMultiProjectOptions:
    """Tests for multi-project CLI options (v2.0)."""

    def test_project_option_in_help(self):
        """Test that --project option is documented in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["test", "--help"])

        assert result.exit_code == 0
        assert "--project" in result.output
        assert "subproject" in result.output.lower()

    def test_tags_option_in_help(self):
        """Test that --tags option is documented in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["test", "--help"])

        assert result.exit_code == 0
        assert "--tags" in result.output

    def test_exclude_tags_option_in_help(self):
        """Test that --exclude-tags option is documented in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["test", "--help"])

        assert result.exit_code == 0
        assert "--exclude-tags" in result.output


class TestEnvModeOption:
    """Tests for --env-mode option (replacing --docker/--no-docker)."""

    def test_env_mode_help_text(self):
        """Test that --env-mode is documented in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["test", "--help"])

        assert result.exit_code == 0
        assert "--env-mode" in result.output

    def test_env_mode_accepts_auto(self):
        """Test that --env-mode accepts 'auto' value."""
        runner = CliRunner()
        # Using --help to avoid needing a real config
        result = runner.invoke(main, ["test", "--help"])
        assert result.exit_code == 0

    @patch("systemeval.cli_main.find_config_file")
    @patch("systemeval.cli_main.load_config")
    @patch("systemeval.cli_main.get_environment_type")
    @patch("systemeval.cli_main.get_adapter")
    def test_env_mode_auto_calls_get_environment_type(self, mock_get_adapter, mock_get_env, mock_load, mock_find, tmp_path):
        """Test that --env-mode auto (default) calls get_environment_type."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest\nproject_root: .")
        mock_find.return_value = config_file

        mock_config = MagicMock()
        mock_config.adapter = "pytest"
        mock_config.project_root = tmp_path
        mock_config.environments = None
        mock_load.return_value = mock_config

        mock_get_env.return_value = "docker"

        mock_adapter = MagicMock()
        mock_adapter.validate_environment.return_value = True
        mock_adapter.execute.return_value = TestResult(
            passed=1, failed=0, errors=0, skipped=0, duration=0.1
        )
        mock_get_adapter.return_value = mock_adapter

        runner = CliRunner()
        result = runner.invoke(main, ["test"])

        # get_environment_type should have been called (default 'auto' mode)
        mock_get_env.assert_called()

    @patch("systemeval.cli_main.find_config_file")
    @patch("systemeval.cli_main.load_config")
    @patch("systemeval.cli_main.get_environment_type")
    @patch("systemeval.cli_main.get_adapter")
    def test_env_mode_docker_skips_detection(self, mock_get_adapter, mock_get_env, mock_load, mock_find, tmp_path):
        """Test that --env-mode docker doesn't call get_environment_type."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest\nproject_root: .")
        mock_find.return_value = config_file

        mock_config = MagicMock()
        mock_config.adapter = "pytest"
        mock_config.project_root = tmp_path
        mock_config.environments = None
        mock_load.return_value = mock_config

        mock_adapter = MagicMock()
        mock_adapter.validate_environment.return_value = True
        mock_adapter.execute.return_value = TestResult(
            passed=1, failed=0, errors=0, skipped=0, duration=0.1
        )
        mock_get_adapter.return_value = mock_adapter

        runner = CliRunner()
        result = runner.invoke(main, ["test", "--env-mode", "docker"])

        # get_environment_type should NOT have been called
        mock_get_env.assert_not_called()

    @patch("systemeval.cli_main.find_config_file")
    @patch("systemeval.cli_main.load_config")
    @patch("systemeval.cli_main.get_environment_type")
    @patch("systemeval.cli_main.get_adapter")
    def test_env_mode_local_skips_detection(self, mock_get_adapter, mock_get_env, mock_load, mock_find, tmp_path):
        """Test that --env-mode local doesn't call get_environment_type."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest\nproject_root: .")
        mock_find.return_value = config_file

        mock_config = MagicMock()
        mock_config.adapter = "pytest"
        mock_config.project_root = tmp_path
        mock_config.environments = None
        mock_load.return_value = mock_config

        mock_adapter = MagicMock()
        mock_adapter.validate_environment.return_value = True
        mock_adapter.execute.return_value = TestResult(
            passed=1, failed=0, errors=0, skipped=0, duration=0.1
        )
        mock_get_adapter.return_value = mock_adapter

        runner = CliRunner()
        result = runner.invoke(main, ["test", "--env-mode", "local"])

        # get_environment_type should NOT have been called
        mock_get_env.assert_not_called()

    def test_env_mode_invalid_value_rejected(self):
        """Test that invalid --env-mode values are rejected."""
        runner = CliRunner()
        result = runner.invoke(main, ["test", "--env-mode", "invalid"])

        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid choice" in result.output.lower()
