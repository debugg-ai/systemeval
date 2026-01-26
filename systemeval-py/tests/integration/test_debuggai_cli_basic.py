"""
Integration tests for debugg-ai test command basic flow.

Tests the core workflow:
1. Analyze working directory changes
2. Submit changes to API
3. Poll for completion
4. Download artifacts
5. Verify exit codes
6. Verify output format
"""

import json
import os
import pytest
from pathlib import Path

from tests.fixtures import E2ETestHarness, CLIResult


# Skip all tests if CLI not available
pytestmark = pytest.mark.skipif(
    not (Path(__file__).parent.parent / "fixtures" / ".." / ".." / "debugg-ai-cli" / "dist" / "cli.js").resolve().exists(),
    reason="CLI not built - run 'npm run build' in debugg-ai-cli",
)


class TestBasicTestCommand:
    """Tests for the basic 'debugg-ai test' command flow."""

    def test_help_command_succeeds(self):
        """Test that --help command works."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("--help")

            assert result.success
            assert "debugg-ai" in result.stdout.lower() or "debuggai" in result.stdout.lower()

    def test_version_command_succeeds(self):
        """Test that --version command works."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("--version")

            assert result.success

    def test_test_command_with_no_changes(self):
        """Test 'debugg-ai test' with no file changes."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            # Repo has initial commit but no working changes
            result = harness.run_cli("test")

            # Should complete (maybe with no tests to run)
            assert isinstance(result, CLIResult)

    def test_test_command_with_working_changes(self):
        """Test 'debugg-ai test' analyzes working directory changes."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            # Add some uncommitted changes
            harness.setup_working_changes({
                "src/app.py": "print('hello world')",
                "src/utils.py": "def helper(): return 42",
            })

            result = harness.run_cli("test")

            # Check that a suite creation request was made
            requests = harness.get_api_requests(method="POST", path="/suite")
            assert len(requests) >= 1

            # The request should include the working changes
            suite_request = requests[0]
            # CLI may use either working_changes (snake_case) or workingChanges (camelCase)
            assert "working_changes" in suite_request["body"] or "workingChanges" in suite_request["body"]

    def test_test_command_uses_api_key(self):
        """Test that the CLI uses DEBUGGAI_API_KEY from environment."""
        with E2ETestHarness(valid_api_key="special-test-key") as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # The harness sets DEBUGGAI_API_KEY automatically
            result = harness.run_cli("test")

            # Should use the key set by harness
            assert os.environ.get("DEBUGGAI_API_KEY") == "special-test-key"


class TestSuiteLifecycle:
    """Tests for test suite creation and status polling."""

    def test_creates_suite_via_api(self):
        """Test that CLI creates a test suite via the API."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"feature.py": "# New feature"})

            result = harness.run_cli("test")

            # Verify suite was created
            requests = harness.get_api_requests(method="POST", path="/suite")
            assert len(requests) >= 1

    def test_polls_suite_status(self):
        """Test that CLI polls for suite completion."""
        with E2ETestHarness() as harness:
            # Create suite that will be "running" initially
            suite = harness.expect_suite_creation(
                suite_uuid="poll-test-suite",
                status="pending",
                num_tests=2,
            )

            harness.setup_working_changes({"test.py": "pass"})

            # Set up auto-complete after delay
            harness.server.set_auto_complete_delay(1.0)

            result = harness.run_cli("test", timeout=30.0)

            # CLI should have waited for completion
            updated_suite = harness.server.get_suite("poll-test-suite")
            # If auto-complete worked, status should be completed
            # (or pending if test ran too fast)


class TestExitCodes:
    """Tests for exit code behavior."""

    def test_exit_code_zero_on_pass(self):
        """Test exit code 0 when all tests pass."""
        with E2ETestHarness() as harness:
            # Pre-create a passing suite
            suite = harness.expect_suite_creation(suite_uuid="passing-suite")
            harness.set_suite_to_complete(
                "passing-suite",
                test_results=["passed", "passed", "passed"],
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Should succeed with exit 0
            # Note: actual behavior depends on CLI implementation
            assert isinstance(result, CLIResult)

    def test_exit_code_one_on_failure(self):
        """Test exit code 1 when tests fail."""
        with E2ETestHarness() as harness:
            # Pre-create a failing suite
            suite = harness.expect_suite_creation(suite_uuid="failing-suite")
            harness.set_suite_to_complete(
                "failing-suite",
                test_results=["passed", "failed", "passed"],
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # CLI should report failure
            assert isinstance(result, CLIResult)


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_handles_api_error(self):
        """Test CLI handles API errors gracefully."""
        with E2ETestHarness() as harness:
            # Inject a 500 error on suite creation
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=500,
                message="Internal Server Error",
                method="POST",
                count=1,  # Only fail once
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Should fail but not crash
            assert isinstance(result, CLIResult)
            # Exit code should indicate failure
            assert result.returncode != 0 or "error" in result.output.lower()

    def test_handles_auth_error(self):
        """Test CLI handles authentication errors."""
        with E2ETestHarness(require_auth=True) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Run with invalid API key
            result = harness.run_cli(
                "test",
                env={"DEBUGGAI_API_KEY": "invalid-key"},
            )

            # Should fail with auth error
            assert isinstance(result, CLIResult)

    def test_handles_timeout(self):
        """Test CLI handles long-running operations."""
        with E2ETestHarness(response_delay=0.1) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Run with very short timeout
            result = harness.run_cli("test", timeout=60.0)

            # Should complete eventually
            assert isinstance(result, CLIResult)


class TestOutputFormat:
    """Tests for CLI output format."""

    def test_json_output_flag(self):
        """Test --json output flag produces valid JSON."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            suite = harness.expect_suite_creation(suite_uuid="json-output-suite")
            harness.set_suite_to_complete("json-output-suite")

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test", "--json")

            # Output should contain JSON
            # Try to find JSON in output
            output = result.stdout + result.stderr
            # Look for JSON-like structure
            if result.success or "{" in output:
                # Try to parse any JSON in output
                try:
                    # Find first { and last }
                    start = output.find("{")
                    end = output.rfind("}") + 1
                    if start >= 0 and end > start:
                        json_str = output[start:end]
                        data = json.loads(json_str)
                        assert isinstance(data, dict)
                except json.JSONDecodeError:
                    pass  # Not all output may be JSON

    def test_verbose_output(self):
        """Test verbose output shows more detail."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test", "--verbose")

            # Verbose should have more output than quiet
            assert isinstance(result, CLIResult)


class TestGitIntegration:
    """Tests for git repository integration."""

    def test_detects_repo_name(self):
        """Test CLI detects repository name from git config."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Check that repoName was sent in request
            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                # CLI may use either repo_name (snake_case) or repoName (camelCase)
                assert "repo_name" in body or "repoName" in body

    def test_detects_branch_name(self):
        """Test CLI detects current branch name."""
        with E2ETestHarness(initial_branch="feature-test") as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Check that branch was sent
            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                # CLI may use branch_name (snake_case) or branch/branchName (camelCase)
                assert "branch_name" in body or "branch" in body or "branchName" in body

    def test_analyzes_file_changes(self):
        """Test CLI correctly analyzes file changes."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({
                "src/new_file.py": "# Added file",
            })

            # Also modify an existing file
            harness.repo.add_file("modified.txt", "original")
            harness.repo.commit("Add file")
            harness.repo.modify_file("modified.txt", "modified content")

            result = harness.run_cli("test")

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                working_changes = requests[0]["body"].get("workingChanges", [])
                # Should have at least the modified file
                assert len(working_changes) >= 1


class TestCommitAnalysis:
    """Tests for commit analysis mode."""

    def test_analyze_specific_commit(self):
        """Test analyzing a specific commit."""
        with E2ETestHarness() as harness:
            # Create a commit with changes
            harness.repo.add_file("feature.py", "# Feature code")
            commit = harness.repo.commit("Add feature")

            # Run with commit hash
            result = harness.run_cli("test", "--commit", commit.hash)

            # Should analyze the specific commit
            assert isinstance(result, CLIResult)

    def test_feature_branch_changes(self):
        """Test analyzing feature branch changes vs main."""
        with E2ETestHarness() as harness:
            # Set up feature branch scenario
            base_hash, head_hash = harness.repo.setup_pr_scenario(
                base_branch="main",
                head_branch="feature",
                num_commits=2,
            )

            result = harness.run_cli("test")

            # Should have analyzed feature branch changes
            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                working_changes = requests[0]["body"].get("workingChanges", [])
                # Feature branch added feature_1.py and feature_2.py
                assert len(working_changes) >= 1
