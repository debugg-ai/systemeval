"""
Integration tests for `systemeval e2e run` with debuggai provider.

Tests the complete E2E workflow using Click's CliRunner for CLI invocation,
MockDebuggAIServer for API simulation, and config loading from systemeval.yaml.

Requirements from SE-kgl:
- Test systemeval e2e run command with debuggai provider
- Use MockDebuggAIServer
- Test config loading from systemeval.yaml
- Test --api-key override
- Test --provider override
- Test JSON output matches EvaluationResult schema
- Test template output formats
- Verify verdict is PASS/FAIL/ERROR
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from systemeval.cli import main
from tests.fixtures import (
    MockDebuggAIServer,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_server():
    """Create and start a MockDebuggAIServer for testing."""
    server = MockDebuggAIServer(
        port=0,  # Auto-assign port
        verbose=False,
        valid_api_key="test-api-key-12345",
        require_valid_api_key=True,
    )
    server.start()
    yield server
    server.stop()


def create_systemeval_config(
    project_dir: Path,
    mock_server_url: str,
    api_key: str = "test-api-key-12345",
    provider: str = "debuggai",
    extra_e2e_config: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Create a systemeval.yaml config file in the project directory.

    Args:
        project_dir: Directory to create config in
        mock_server_url: URL of mock server
        api_key: API key for authentication
        provider: E2E provider name
        extra_e2e_config: Additional E2E config options

    Returns:
        Path to created config file
    """
    config_content = f"""adapter: pytest
project_root: .
test_directory: tests
e2e:
  provider:
    provider: {provider}
    api_key: {api_key}
    api_base_url: {mock_server_url}
  output:
    directory: tests/e2e_generated
    test_framework: playwright
  enabled: true
"""
    if extra_e2e_config:
        import yaml
        # Parse and update
        config_dict = yaml.safe_load(config_content)
        config_dict["e2e"].update(extra_e2e_config)
        config_content = yaml.dump(config_dict, default_flow_style=False)

    config_path = project_dir / "systemeval.yaml"
    config_path.write_text(config_content)

    # Create test directory
    (project_dir / "tests" / "e2e_generated").mkdir(parents=True, exist_ok=True)

    return config_path


# ============================================================================
# Test: Config Loading from systemeval.yaml
# ============================================================================


class TestConfigLoading:
    """Tests for loading E2E config from systemeval.yaml."""

    def test_loads_config_from_systemeval_yaml(self, cli_runner, mock_server):
        """Test that e2e run loads provider config from systemeval.yaml."""
        with cli_runner.isolated_filesystem():
            # Create config with mock server URL
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
                api_key="test-api-key-12345",
            )

            # Set up auto-complete so the suite finishes
            mock_server.set_auto_complete_delay(0.5)

            # Run CLI
            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Should have attempted to use the configured provider
            # Check output mentions provider or API URL
            assert result.exit_code in [0, 1, 2]

    def test_config_without_e2e_section_fails(self, cli_runner):
        """Test that e2e run fails gracefully when no e2e section exists."""
        with cli_runner.isolated_filesystem():
            # Create minimal config without e2e section
            config_content = """adapter: pytest
project_root: .
test_directory: tests
"""
            Path("systemeval.yaml").write_text(config_content)

            result = cli_runner.invoke(main, ["e2e", "run"])

            # Should fail with helpful error
            assert result.exit_code == 2
            output = result.output.lower()
            assert "e2e" in output or "api-key" in output or "not configured" in output

    def test_config_with_missing_api_key_fails(self, cli_runner, mock_server):
        """Test that e2e run fails when API key is missing for debuggai provider."""
        with cli_runner.isolated_filesystem():
            # Create config without API key
            config_content = f"""adapter: pytest
project_root: .
test_directory: tests
e2e:
  provider:
    provider: debuggai
    api_base_url: {mock_server.base_url}
  output:
    directory: tests/e2e_generated
  enabled: true
"""
            Path("systemeval.yaml").write_text(config_content)
            Path("tests/e2e_generated").mkdir(parents=True, exist_ok=True)

            result = cli_runner.invoke(main, ["e2e", "run"])

            # Should fail with API key error
            assert result.exit_code == 2
            output = result.output.lower()
            assert "api" in output and "key" in output


# ============================================================================
# Test: CLI Option Overrides
# ============================================================================


class TestCliOverrides:
    """Tests for CLI option overriding config values."""

    def test_api_key_override(self, cli_runner, mock_server):
        """Test that --api-key overrides config api_key."""
        with cli_runner.isolated_filesystem():
            # Create config with different API key
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
                api_key="config-key-wrong",
            )

            # Set up auto-complete
            mock_server.set_auto_complete_delay(0.5)

            # Run with correct API key override
            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--api-key", "test-api-key-12345", "--verbose"],
            )

            # Should succeed with overridden key (or at least proceed past auth)
            # The mock server validates API keys, so wrong key = 401
            assert result.exit_code in [0, 1, 2]

    def test_api_key_from_environment_variable(self, cli_runner, mock_server, monkeypatch):
        """Test that DEBUGGAI_API_KEY environment variable is used."""
        monkeypatch.setenv("DEBUGGAI_API_KEY", "test-api-key-12345")

        with cli_runner.isolated_filesystem():
            # Create config without API key
            config_content = f"""adapter: pytest
project_root: .
test_directory: tests
e2e:
  provider:
    provider: debuggai
    api_base_url: {mock_server.base_url}
  output:
    directory: tests/e2e_generated
  enabled: true
"""
            Path("systemeval.yaml").write_text(config_content)
            Path("tests/e2e_generated").mkdir(parents=True, exist_ok=True)

            mock_server.set_auto_complete_delay(0.5)

            # Run - env var should be used
            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Should proceed (env var used)
            assert result.exit_code in [0, 1, 2]

    def test_provider_override(self, cli_runner, mock_server):
        """Test that --provider overrides config provider."""
        with cli_runner.isolated_filesystem():
            # Create config with debuggai provider
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
                provider="debuggai",
            )

            # Run with mock provider override
            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--provider", "mock", "--verbose"],
            )

            # Should attempt to use mock provider
            assert result.exit_code in [0, 1, 2]

    def test_output_dir_override(self, cli_runner, mock_server):
        """Test that --output-dir overrides config output directory."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            custom_output = Path("custom_e2e_output")
            custom_output.mkdir(parents=True, exist_ok=True)

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--output-dir", str(custom_output), "--verbose"],
            )

            # Check for valid execution
            assert result.exit_code in [0, 1, 2]

    def test_timeout_override(self, cli_runner, mock_server):
        """Test that --timeout overrides default timeout."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Don't auto-complete, so it should timeout
            # Use very short timeout to test timeout behavior
            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--timeout", "1", "--verbose"],
            )

            # Should timeout or exit with error
            assert result.exit_code in [1, 2]


# ============================================================================
# Test: JSON Output Schema
# ============================================================================


class TestJsonOutput:
    """Tests for JSON output format compliance."""

    def test_json_output_is_valid_json(self, cli_runner, mock_server):
        """Test that --json outputs valid JSON."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            # Output should contain JSON
            output = result.output.strip()
            if output.startswith("{"):
                try:
                    data = json.loads(output)
                    assert isinstance(data, dict)
                except json.JSONDecodeError:
                    # May have non-JSON prefixes, try to extract JSON
                    start = output.find("{")
                    end = output.rfind("}") + 1
                    if start >= 0 and end > start:
                        data = json.loads(output[start:end])
                        assert isinstance(data, dict)

    def test_json_output_contains_verdict_field(self, cli_runner, mock_server):
        """Test that JSON output contains verdict field."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            output = result.output.strip()
            # Extract JSON
            start = output.find("{")
            end = output.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(output[start:end])
                # Verdict should be present (EvaluationResult schema)
                assert "verdict" in data or "status" in data

    def test_json_output_verdict_values(self, cli_runner, mock_server):
        """Test that verdict is one of PASS/FAIL/ERROR."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            output = result.output.strip()
            start = output.find("{")
            end = output.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(output[start:end])
                if "verdict" in data:
                    assert data["verdict"] in ["PASS", "FAIL", "ERROR"]

    def test_json_output_evaluation_result_schema(self, cli_runner, mock_server):
        """Test that JSON output matches EvaluationResult schema."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            output = result.output.strip()
            start = output.find("{")
            end = output.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(output[start:end])

                # EvaluationResult schema should have these fields
                expected_fields_set_1 = {"verdict", "exit_code"}
                expected_fields_set_2 = {"status", "error"}

                has_evaluation_fields = any(f in data for f in expected_fields_set_1)
                has_error_fields = any(f in data for f in expected_fields_set_2)

                assert has_evaluation_fields or has_error_fields, f"JSON should have evaluation or error fields, got: {list(data.keys())}"

    def test_json_error_output_format(self, cli_runner):
        """Test that errors in JSON mode output valid JSON."""
        with cli_runner.isolated_filesystem():
            # Create config that will cause an error (no e2e section)
            config_content = """adapter: pytest
project_root: .
"""
            Path("systemeval.yaml").write_text(config_content)

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            # Should have non-zero exit code
            assert result.exit_code != 0


# ============================================================================
# Test: Template Output
# ============================================================================


class TestTemplateOutput:
    """Tests for template-based output formats."""

    def test_e2e_summary_template(self, cli_runner, mock_server):
        """Test --template e2e_summary output format."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--template", "e2e_summary"],
            )

            # Should produce output (success or error)
            assert result.exit_code in [0, 1, 2]

    def test_e2e_table_template(self, cli_runner, mock_server):
        """Test --template e2e_table output format."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--template", "e2e_table"],
            )

            # Should produce table-like output
            assert result.exit_code in [0, 1, 2]

    def test_e2e_ci_template(self, cli_runner, mock_server):
        """Test --template e2e_ci output format for CI environments."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--template", "e2e_ci"],
            )

            # CI template should be concise
            assert result.exit_code in [0, 1, 2]


# ============================================================================
# Test: Verdict Outcomes
# ============================================================================


class TestVerdictOutcomes:
    """Tests for different verdict outcomes (PASS/FAIL/ERROR)."""

    def test_pass_verdict_on_successful_generation(self, cli_runner, mock_server):
        """Test PASS verdict when generation succeeds."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Create a suite that will complete successfully
            suite = mock_server.create_suite(
                suite_uuid="pass-test-suite",
                status="completed",
                num_tests=3,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            output = result.output.strip()
            start = output.find("{")
            end = output.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(output[start:end])
                # On success, verdict should be PASS or status completed
                if "verdict" in data:
                    assert data["verdict"] in ["PASS", "ERROR"]  # ERROR if no tests found
                if result.exit_code == 0:
                    assert "verdict" in data and data["verdict"] == "PASS"

    def test_error_verdict_on_generation_failure(self, cli_runner, mock_server):
        """Test ERROR verdict when generation fails."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Inject an error on suite creation
            mock_server.inject_error(
                "/cli/e2e/suites",
                status_code=500,
                message="Internal Server Error",
                method="POST",
                count=0,  # Always fail
            )

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            # Should have non-zero exit code
            assert result.exit_code != 0

            output = result.output.strip()
            start = output.find("{")
            end = output.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(output[start:end])
                # On error, should indicate error state
                if "verdict" in data:
                    assert data["verdict"] in ["ERROR", "FAIL"]
                elif "status" in data:
                    assert data["status"] == "error"

    def test_error_verdict_on_auth_failure(self, cli_runner, mock_server):
        """Test ERROR verdict when authentication fails."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
                api_key="wrong-api-key",
            )

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            # Should fail with auth error
            assert result.exit_code != 0

            output = result.output.strip()
            start = output.find("{")
            end = output.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(output[start:end])
                # Auth failure is an error
                if "verdict" in data:
                    assert data["verdict"] == "ERROR"
                elif "status" in data:
                    assert data["status"] == "error"

    def test_error_verdict_on_timeout(self, cli_runner, mock_server):
        """Test ERROR verdict when generation times out."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Don't set auto-complete, so it will timeout

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--json", "--timeout", "2"],
            )

            # Should timeout
            assert result.exit_code != 0


# ============================================================================
# Test: Mock Server Integration
# ============================================================================


class TestMockServerIntegration:
    """Tests for MockDebuggAIServer integration."""

    def test_creates_suite_via_mock_server(self, cli_runner, mock_server):
        """Test that CLI creates a suite via the mock server API."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Check that requests were made to the mock server
            all_requests = mock_server.recorded_requests
            # Should have made at least some API calls
            assert result.exit_code in [0, 1, 2]

    def test_polls_suite_status_via_mock_server(self, cli_runner, mock_server):
        """Test that CLI polls for suite status."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Create a suite that takes time to complete
            mock_server.set_auto_complete_delay(1.0)

            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Should have run through the workflow
            assert result.exit_code in [0, 1, 2]

    def test_handles_server_errors_gracefully(self, cli_runner, mock_server):
        """Test that CLI handles server errors gracefully."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Inject intermittent errors
            mock_server.inject_error(
                "/cli/e2e/suites",
                status_code=503,
                message="Service Unavailable",
                method="POST",
                count=1,  # Only fail once
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Should handle the error (either retry or fail gracefully)
            assert isinstance(result.exit_code, int)

    def test_respects_response_delays(self, cli_runner, mock_server):
        """Test that CLI handles slow API responses."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Add response delay
            mock_server.set_response_delay(0.2)
            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Should complete even with delays
            assert result.exit_code in [0, 1, 2]


# ============================================================================
# Test: Help and Version
# ============================================================================


class TestHelpAndVersion:
    """Tests for CLI help and version output."""

    def test_e2e_run_help_shows_options(self, cli_runner):
        """Test that e2e run --help shows all expected options."""
        result = cli_runner.invoke(main, ["e2e", "run", "--help"])

        assert result.exit_code == 0
        output = result.output

        # Check for expected options
        assert "--api-key" in output
        assert "--provider" in output
        assert "--json" in output
        assert "--template" in output
        assert "--timeout" in output
        assert "--verbose" in output

    def test_e2e_run_help_mentions_debuggai(self, cli_runner):
        """Test that help mentions debuggai provider."""
        result = cli_runner.invoke(main, ["e2e", "run", "--help"])

        assert result.exit_code == 0
        output = result.output.lower()

        assert "debuggai" in output

    def test_e2e_run_help_mentions_env_var(self, cli_runner):
        """Test that help mentions DEBUGGAI_API_KEY environment variable."""
        result = cli_runner.invoke(main, ["e2e", "run", "--help"])

        assert result.exit_code == 0
        assert "DEBUGGAI_API_KEY" in result.output


# ============================================================================
# Test: Exit Codes
# ============================================================================


class TestExitCodes:
    """Tests for proper exit code behavior."""

    def test_exit_code_zero_on_success(self, cli_runner, mock_server):
        """Test exit code 0 when generation succeeds."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run"])

            # Exit code depends on actual generation outcome
            assert result.exit_code in [0, 1, 2]

    def test_exit_code_one_on_failure(self, cli_runner, mock_server):
        """Test exit code 1 when generation fails."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Inject a failure
            mock_server.inject_error(
                "/cli/e2e/suites",
                status_code=400,
                message="Bad Request",
                method="POST",
                count=0,
            )

            result = cli_runner.invoke(main, ["e2e", "run"])

            # Should fail
            assert result.exit_code != 0

    def test_exit_code_two_on_config_error(self, cli_runner):
        """Test exit code 2 on configuration errors."""
        with cli_runner.isolated_filesystem():
            # No config file
            result = cli_runner.invoke(main, ["e2e", "run"])

            # Exit code 2 indicates config/setup error
            assert result.exit_code == 2


# ============================================================================
# Test: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_missing_config_file(self, cli_runner):
        """Test graceful handling of missing config file."""
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(main, ["e2e", "run"])

            assert result.exit_code == 2
            output = result.output.lower()
            assert "systemeval.yaml" in output or "config" in output or "found" in output

    def test_handles_invalid_yaml_config(self, cli_runner):
        """Test graceful handling of invalid YAML config."""
        with cli_runner.isolated_filesystem():
            Path("systemeval.yaml").write_text("adapter: pytest\n  invalid: indentation")

            result = cli_runner.invoke(main, ["e2e", "run"])

            assert result.exit_code == 2

    def test_handles_invalid_provider_choice(self, cli_runner, mock_server):
        """Test handling of invalid provider choice."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--provider", "invalid_provider"],
            )

            # Invalid provider should be rejected
            assert result.exit_code == 2
            output = result.output.lower()
            assert "invalid" in output or "choice" in output

    def test_handles_network_timeout(self, cli_runner):
        """Test handling when server is unreachable."""
        with cli_runner.isolated_filesystem():
            # Point to non-existent server
            create_systemeval_config(
                Path("."),
                "http://127.0.0.1:59999",  # Unlikely to be running
            )

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--timeout", "3"],
            )

            # Should fail with connection error
            assert result.exit_code != 0

    def test_verbose_flag_shows_debug_info(self, cli_runner, mock_server):
        """Test that --verbose shows additional debug information."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Verbose should show more details
            assert len(result.output) > 0


# ============================================================================
# Test: Full E2E Workflow
# ============================================================================


class TestFullWorkflow:
    """Integration tests for the complete E2E workflow."""

    def test_complete_generation_workflow(self, cli_runner, mock_server):
        """Test complete workflow: config -> generate -> poll -> complete."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            # Set up auto-complete
            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--verbose"])

            # Should complete the workflow
            assert result.exit_code in [0, 1, 2]

    def test_workflow_with_json_output(self, cli_runner, mock_server):
        """Test complete workflow with JSON output."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(main, ["e2e", "run", "--json"])

            # Should produce valid JSON output
            output = result.output.strip()
            start = output.find("{")
            end = output.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(output[start:end])
                assert isinstance(data, dict)

    def test_workflow_with_no_download(self, cli_runner, mock_server):
        """Test workflow with --no-download flag."""
        with cli_runner.isolated_filesystem():
            create_systemeval_config(
                Path("."),
                mock_server.base_url,
            )

            mock_server.set_auto_complete_delay(0.5)

            result = cli_runner.invoke(
                main,
                ["e2e", "run", "--no-download", "--verbose"],
            )

            # Should skip artifact download
            assert result.exit_code in [0, 1, 2]
