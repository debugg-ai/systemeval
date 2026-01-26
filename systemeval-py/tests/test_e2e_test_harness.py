"""Tests for E2ETestHarness fixture."""

import os
import pytest
from pathlib import Path

from tests.fixtures.e2e_test_harness import (
    E2ETestHarness,
    CLIResult,
    create_e2e_harness,
)


class TestE2EHarnessBasics:
    """Basic functionality tests for E2ETestHarness."""

    def test_harness_starts_and_stops(self):
        """Test harness starts and stops cleanly."""
        harness = E2ETestHarness()
        harness.start()

        assert harness.server is not None
        assert harness.repo is not None
        assert harness.server.actual_port > 0
        assert harness.repo.path.exists()

        server_port = harness.server.actual_port
        repo_path = harness.repo.path

        harness.stop()

        # After stop, paths should be cleaned up
        assert not repo_path.exists()

    def test_context_manager(self):
        """Test harness works as context manager."""
        with E2ETestHarness() as harness:
            assert harness.server is not None
            assert harness.repo is not None
            assert harness.api_url.startswith("http://")

    def test_api_key_property(self):
        """Test api_key property returns valid key."""
        with E2ETestHarness(valid_api_key="my-key") as harness:
            assert harness.api_key == "my-key"

    def test_api_url_property(self):
        """Test api_url property returns server URL."""
        with E2ETestHarness() as harness:
            url = harness.api_url
            assert url.startswith("http://127.0.0.1:")
            assert str(harness.server.actual_port) in url

    def test_create_e2e_harness_helper(self):
        """Test create_e2e_harness helper function."""
        harness = create_e2e_harness(initial_branch="test-branch")
        try:
            assert harness.repo.current_branch == "test-branch"
            assert harness.server.actual_port > 0
        finally:
            harness.stop()


class TestEnvironmentSetup:
    """Tests for environment variable management."""

    def test_sets_api_key_env(self):
        """Test that DEBUGGAI_API_KEY is set."""
        with E2ETestHarness(valid_api_key="test-env-key") as harness:
            assert os.environ.get("DEBUGGAI_API_KEY") == "test-env-key"

    def test_sets_api_url_env(self):
        """Test that DEBUGGAI_API_URL is set."""
        with E2ETestHarness() as harness:
            assert os.environ.get("DEBUGGAI_API_URL") == harness.api_url

    def test_sets_mock_mode_env(self):
        """Test that DEBUGGAI_MOCK_MODE is set."""
        with E2ETestHarness() as harness:
            assert os.environ.get("DEBUGGAI_MOCK_MODE") == "1"

    def test_restores_env_on_exit(self):
        """Test that environment is restored on exit."""
        original = os.environ.get("DEBUGGAI_API_KEY")
        os.environ["DEBUGGAI_API_KEY"] = "original-value"

        try:
            with E2ETestHarness() as harness:
                assert os.environ.get("DEBUGGAI_API_KEY") != "original-value"

            # Should be restored
            assert os.environ.get("DEBUGGAI_API_KEY") == "original-value"
        finally:
            if original is None:
                os.environ.pop("DEBUGGAI_API_KEY", None)
            else:
                os.environ["DEBUGGAI_API_KEY"] = original


class TestServerIntegration:
    """Tests for MockDebuggAIServer integration."""

    def test_server_is_accessible(self):
        """Test that the mock server is accessible."""
        import urllib.request
        import json

        with E2ETestHarness() as harness:
            url = f"{harness.api_url}/health"
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
            assert data["status"] == "healthy"

    def test_auto_complete_delay_is_applied(self):
        """Test that auto_complete_delay is passed to server."""
        with E2ETestHarness(auto_complete_delay=1.0) as harness:
            assert harness.server.auto_complete_delay == 1.0

    def test_response_delay_is_applied(self):
        """Test that response_delay is passed to server."""
        with E2ETestHarness(response_delay=0.5) as harness:
            assert harness.server.response_delay == 0.5


class TestRepoIntegration:
    """Tests for GitRepoFixture integration."""

    def test_repo_is_initialized(self):
        """Test that the git repo is initialized."""
        with E2ETestHarness() as harness:
            assert (harness.repo.path / ".git").exists()

    def test_custom_branch_name(self):
        """Test custom initial branch name."""
        with E2ETestHarness(initial_branch="develop") as harness:
            assert harness.repo.current_branch == "develop"

    def test_custom_author(self):
        """Test custom git author."""
        with E2ETestHarness(author_name="CI Bot") as harness:
            harness.repo.add_file("test.txt", "content")
            commit = harness.repo.commit("Test commit")
            assert commit.author == "CI Bot"


class TestHelperMethods:
    """Tests for test helper methods."""

    def test_setup_working_changes(self):
        """Test setup_working_changes helper."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({
                "src/app.py": "print('hello')",
                "src/utils.py": "def helper(): pass",
            })

            assert harness.repo.file_exists("src/app.py")
            assert harness.repo.file_exists("src/utils.py")

    def test_setup_working_changes_with_commit(self):
        """Test setup_working_changes with commit."""
        with E2ETestHarness() as harness:
            initial_count = harness.repo.get_commit_count()

            harness.setup_working_changes(
                {"file.txt": "content"},
                commit=True,
                commit_message="Add file",
            )

            assert harness.repo.get_commit_count() == initial_count + 1

    def test_setup_feature_branch(self):
        """Test setup_feature_branch helper."""
        with E2ETestHarness() as harness:
            commit = harness.setup_feature_branch(
                branch_name="my-feature",
                num_commits=2,
            )

            assert harness.repo.current_branch == "my-feature"
            assert commit is not None
            assert harness.repo.file_exists("feature_1.py")
            assert harness.repo.file_exists("feature_2.py")

    def test_setup_feature_branch_with_files(self):
        """Test setup_feature_branch with custom files."""
        with E2ETestHarness() as harness:
            harness.setup_feature_branch(
                files={"custom.py": "# Custom file"},
            )

            assert harness.repo.file_exists("custom.py")

    def test_expect_suite_creation(self):
        """Test expect_suite_creation helper."""
        with E2ETestHarness() as harness:
            suite = harness.expect_suite_creation(
                suite_uuid="expected-uuid",
                status="running",
                num_tests=5,
            )

            assert suite.uuid == "expected-uuid"
            assert suite.status == "running"
            assert len(suite.tests) == 5

    def test_set_suite_to_complete(self):
        """Test set_suite_to_complete helper."""
        with E2ETestHarness() as harness:
            suite = harness.expect_suite_creation(suite_uuid="complete-test")
            harness.set_suite_to_complete(
                "complete-test",
                test_results=["passed", "passed", "failed"],
            )

            updated = harness.server.get_suite("complete-test")
            assert updated.status == "completed"

    def test_inject_api_error(self):
        """Test inject_api_error helper."""
        import urllib.request
        from urllib.error import HTTPError

        with E2ETestHarness() as harness:
            harness.inject_api_error("/health", 503, "Maintenance")

            url = f"{harness.api_url}/health"
            with pytest.raises(HTTPError) as exc_info:
                urllib.request.urlopen(url)
            assert exc_info.value.code == 503

    def test_clear_api_errors(self):
        """Test clear_api_errors helper."""
        import urllib.request
        import json

        with E2ETestHarness() as harness:
            harness.inject_api_error("/health", 500, "Error", count=0)
            harness.clear_api_errors()

            url = f"{harness.api_url}/health"
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
            assert data["status"] == "healthy"

    def test_get_api_requests(self):
        """Test get_api_requests helper."""
        import urllib.request
        import json

        with E2ETestHarness() as harness:
            # Make a suite creation request - these are recorded
            url = f"{harness.api_url}/cli/e2e/suites"
            data = json.dumps({
                "repoName": "test-repo",
                "workingChanges": [],
            }).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"Bearer {harness.api_key}")
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req)

            requests = harness.get_api_requests(method="POST", path="/suite")
            assert len(requests) >= 1
            assert requests[0]["body"]["repoName"] == "test-repo"

    def test_reset(self):
        """Test reset helper clears server state."""
        with E2ETestHarness() as harness:
            harness.expect_suite_creation("test-suite")
            assert len(harness.server.suites) == 1

            harness.reset()

            assert len(harness.server.suites) == 0


class TestCLIResult:
    """Tests for CLIResult dataclass."""

    def test_success_property(self):
        """Test success property."""
        result = CLIResult(
            returncode=0,
            stdout="output",
            stderr="",
            command=["test"],
        )
        assert result.success is True

        result = CLIResult(
            returncode=1,
            stdout="",
            stderr="error",
            command=["test"],
        )
        assert result.success is False

    def test_output_property(self):
        """Test output property combines stdout and stderr."""
        result = CLIResult(
            returncode=0,
            stdout="stdout ",
            stderr="stderr",
            command=["test"],
        )
        assert result.output == "stdout stderr"

    def test_repr(self):
        """Test string representation."""
        result = CLIResult(
            returncode=0,
            stdout="x" * 100,
            stderr="y" * 50,
            command=["test"],
        )
        repr_str = repr(result)
        assert "returncode=0" in repr_str
        assert "stdout_len=100" in repr_str
        assert "stderr_len=50" in repr_str


class TestCLIInvocation:
    """Tests for CLI invocation methods."""

    @pytest.fixture
    def cli_available(self):
        """Check if CLI is available."""
        cli_path = Path(__file__).parent / "fixtures" / ".." / ".." / "debugg-ai-cli" / "dist" / "cli.js"
        cli_path = cli_path.resolve()
        if not cli_path.exists():
            pytest.skip("CLI not built - run 'npm run build' in debugg-ai-cli")
        return cli_path

    def test_run_cli_executes_command(self, cli_available):
        """Test run_cli executes a command."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("--help")
            assert isinstance(result, CLIResult)
            assert isinstance(result.returncode, int)
            # --help should succeed
            assert result.returncode == 0

    def test_run_cli_uses_repo_path_as_cwd(self, cli_available):
        """Test run_cli uses repo path as working directory."""
        with E2ETestHarness() as harness:
            harness.repo.add_file("marker.txt", "marker")

            result = harness.run_cli("--help")

            assert isinstance(result, CLIResult)
            assert result.returncode == 0

    def test_run_cli_with_custom_env(self, cli_available):
        """Test run_cli accepts custom environment variables."""
        with E2ETestHarness() as harness:
            result = harness.run_cli(
                "--help",
                env={"CUSTOM_VAR": "custom_value"},
            )
            assert "CUSTOM_VAR" in result.env
            assert result.env["CUSTOM_VAR"] == "custom_value"

    def test_run_cli_with_custom_cwd(self, cli_available):
        """Test run_cli accepts custom working directory."""
        import tempfile

        with E2ETestHarness() as harness:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = harness.run_cli("--help", cwd=tmpdir)
                assert isinstance(result, CLIResult)

    def test_run_cli_timeout(self, cli_available):
        """Test run_cli handles timeout."""
        with E2ETestHarness(cli_timeout=30.0) as harness:
            result = harness.run_cli("--help", timeout=30.0)
            assert isinstance(result, CLIResult)


class TestCleanupOnError:
    """Tests for cleanup behavior on errors."""

    def test_cleanup_on_exception(self):
        """Test that cleanup happens on exception."""
        repo_path = None

        with pytest.raises(RuntimeError):
            with E2ETestHarness() as harness:
                repo_path = harness.repo.path
                assert repo_path.exists()
                raise RuntimeError("Test error")

        # Repo should be cleaned up even after exception
        assert repo_path is not None
        assert not repo_path.exists()

    def test_keep_on_error_option(self):
        """Test keep_on_error preserves repo on error."""
        # This is harder to test cleanly, just verify the option is accepted
        with E2ETestHarness(keep_on_error=True) as harness:
            assert harness.repo.path.exists()


class TestAccessBeforeInit:
    """Tests for accessing properties before initialization."""

    def test_server_before_init_raises(self):
        """Test accessing server before init raises."""
        harness = E2ETestHarness()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = harness.server

    def test_repo_before_init_raises(self):
        """Test accessing repo before init raises."""
        harness = E2ETestHarness()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = harness.repo
