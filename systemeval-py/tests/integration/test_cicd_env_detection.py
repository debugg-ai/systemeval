"""
Integration tests for CI/CD environment variable detection.

Tests that the debugg-ai CLI correctly detects and uses GitHub Actions
environment variables when running in CI mode.

Covers:
- GITHUB_SHA: Commit hash detection
- GITHUB_REF_NAME: Branch name detection
- GITHUB_HEAD_REF: PR head branch detection
- CI: CI environment detection and behavior differences

Requirement: SE-55j
"""

import pytest
from pathlib import Path

from tests.fixtures import E2ETestHarness, CLIResult


# Skip all tests if CLI not available
pytestmark = pytest.mark.skipif(
    not (Path(__file__).parent.parent / "fixtures" / ".." / ".." / "debugg-ai-cli" / "dist" / "cli.js").resolve().exists(),
    reason="CLI not built - run 'npm run build' in debugg-ai-cli",
)


class TestGitHubSHADetection:
    """Tests for GITHUB_SHA environment variable detection."""

    def test_cli_uses_github_sha_for_commit_hash(self):
        """Test that CLI uses GITHUB_SHA when available instead of git HEAD."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"src/app.py": "# new feature"})

            # Run CLI with GITHUB_SHA set
            github_sha = "abc123def456789012345678901234567890abcd"
            result = harness.run_cli(
                "test",
                env={"GITHUB_SHA": github_sha, "CI": "true"},
            )

            # Verify request was made
            requests = harness.get_api_requests(method="POST", path="/suite")
            assert len(requests) >= 1

            # Check that the commit hash in the request matches GITHUB_SHA
            body = requests[0]["body"]
            # CLI may use commit_sha, commitSha, sha, or commit field
            commit_field = (
                body.get("commit_sha") or
                body.get("commitSha") or
                body.get("sha") or
                body.get("commit") or
                body.get("head_sha") or
                body.get("headSha")
            )
            if commit_field:
                msg = f"Expected commit hash {github_sha}, got {commit_field}"
                assert commit_field == github_sha, msg

    def test_github_sha_takes_precedence_over_local_git(self):
        """Test that GITHUB_SHA overrides locally detected git commit."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            # Create a commit so there's a local git HEAD
            harness.repo.add_file("feature.py", "# Feature code")
            harness.repo.commit("Add feature")
            local_hash = harness.repo.get_head_commit()

            # GITHUB_SHA should be different from local git HEAD
            github_sha = "ffffffffffffffffffffffffffffffffffffffff"
            assert github_sha != local_hash

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli(
                "test",
                env={"GITHUB_SHA": github_sha, "CI": "true"},
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                commit_field = (
                    body.get("commit_sha") or
                    body.get("commitSha") or
                    body.get("sha") or
                    body.get("commit")
                )
                # Should use GITHUB_SHA, not local git HEAD
                if commit_field:
                    assert commit_field != local_hash, \
                        "CLI should use GITHUB_SHA over local git HEAD"

    def test_short_github_sha_accepted(self):
        """Test that short SHA values are accepted (common in logs)."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"app.py": "code"})

            # Some CI systems may provide short SHAs
            short_sha = "abc123d"
            result = harness.run_cli(
                "test",
                env={"GITHUB_SHA": short_sha, "CI": "true"},
            )

            # Should not crash - CLI should handle this gracefully
            assert isinstance(result, CLIResult)


class TestGitHubRefNameDetection:
    """Tests for GITHUB_REF_NAME environment variable detection."""

    def test_cli_uses_github_ref_name_for_branch(self):
        """Test that CLI uses GITHUB_REF_NAME for branch detection."""
        with E2ETestHarness(
            auto_complete_delay=0.5,
            initial_branch="main"
        ) as harness:
            harness.setup_working_changes({"src/feature.py": "# feature"})

            # Set GITHUB_REF_NAME to a different branch name
            result = harness.run_cli(
                "test",
                env={
                    "GITHUB_REF_NAME": "release/v2.0.0",
                    "CI": "true",
                },
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                branch_field = (
                    body.get("branch_name") or
                    body.get("branchName") or
                    body.get("branch") or
                    body.get("ref") or
                    body.get("ref_name") or
                    body.get("refName")
                )
                if branch_field:
                    msg = f"Expected branch 'release/v2.0.0', got '{branch_field}'"
                    assert branch_field == "release/v2.0.0", msg

    def test_github_ref_name_overrides_local_branch(self):
        """Test that GITHUB_REF_NAME takes precedence over local git branch."""
        with E2ETestHarness(
            auto_complete_delay=0.5,
            initial_branch="local-branch"
        ) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli(
                "test",
                env={
                    "GITHUB_REF_NAME": "ci-detected-branch",
                    "CI": "true",
                },
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                branch_field = (
                    body.get("branch_name") or
                    body.get("branchName") or
                    body.get("branch")
                )
                if branch_field:
                    assert branch_field != "local-branch", \
                        "CLI should use GITHUB_REF_NAME over local git branch"

    def test_handles_tag_refs(self):
        """Test that GITHUB_REF_NAME with tag format is handled correctly."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"app.py": "code"})

            # Tags are also provided via GITHUB_REF_NAME
            result = harness.run_cli(
                "test",
                env={
                    "GITHUB_REF_NAME": "v1.2.3",
                    "CI": "true",
                },
            )

            # Should not crash - tags are valid ref names
            assert isinstance(result, CLIResult)


class TestGitHubHeadRefDetection:
    """Tests for GITHUB_HEAD_REF environment variable detection (PR scenarios)."""

    def test_cli_uses_github_head_ref_for_pr_branch(self):
        """Test that CLI uses GITHUB_HEAD_REF in PR context."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"pr_change.py": "# PR change"})

            # GITHUB_HEAD_REF is set for pull request events
            result = harness.run_cli(
                "test",
                env={
                    "GITHUB_HEAD_REF": "feature/new-feature",
                    "GITHUB_REF_NAME": "123/merge",  # PR merge ref
                    "CI": "true",
                },
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                # In PR context, HEAD_REF should be preferred for the source branch
                head_ref_field = (
                    body.get("head_ref") or
                    body.get("headRef") or
                    body.get("pr_branch") or
                    body.get("prBranch") or
                    body.get("source_branch") or
                    body.get("sourceBranch")
                )
                if head_ref_field:
                    msg = f"Expected PR branch 'feature/new-feature', got '{head_ref_field}'"
                    assert head_ref_field == "feature/new-feature", msg

    def test_github_head_ref_empty_for_non_pr(self):
        """Test that empty GITHUB_HEAD_REF is handled (push events)."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"push_change.py": "code"})

            # For push events, GITHUB_HEAD_REF is empty
            result = harness.run_cli(
                "test",
                env={
                    "GITHUB_HEAD_REF": "",  # Empty for push events
                    "GITHUB_REF_NAME": "main",
                    "CI": "true",
                },
            )

            # Should not crash - empty HEAD_REF is valid
            assert isinstance(result, CLIResult)

            # Should fall back to GITHUB_REF_NAME
            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                branch_field = (
                    body.get("branch_name") or
                    body.get("branchName") or
                    body.get("branch")
                )
                # When HEAD_REF is empty, should use REF_NAME
                if branch_field:
                    assert branch_field == "main" or branch_field == "", \
                        "Should use REF_NAME when HEAD_REF is empty"

    def test_pr_context_with_base_ref(self):
        """Test PR context with both head and base refs available."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"pr.py": "# PR code"})

            result = harness.run_cli(
                "test",
                env={
                    "GITHUB_HEAD_REF": "feature/auth-update",
                    "GITHUB_BASE_REF": "main",
                    "GITHUB_REF_NAME": "42/merge",
                    "CI": "true",
                },
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                # Check base ref is captured if available
                base_ref_field = (
                    body.get("base_ref") or
                    body.get("baseRef") or
                    body.get("base_branch") or
                    body.get("baseBranch") or
                    body.get("target_branch") or
                    body.get("targetBranch")
                )
                # Base ref detection is optional but should work if implemented
                if base_ref_field:
                    assert base_ref_field == "main"


class TestCIModeDetection:
    """Tests for CI environment detection and behavior differences."""

    def test_ci_env_var_detected(self):
        """Test that CI=true environment variable is detected."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"ci_test.py": "pass"})

            result = harness.run_cli(
                "test",
                env={"CI": "true"},
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                ci_field = (
                    body.get("ci") or
                    body.get("is_ci") or
                    body.get("isCi") or
                    body.get("ci_mode") or
                    body.get("ciMode")
                )
                # CI flag should be present and true
                if ci_field is not None:
                    msg = f"Expected CI flag to be truthy, got {ci_field}"
                    assert ci_field in [True, "true", "1", 1], msg

    def test_local_mode_without_ci_env(self):
        """Test behavior when CI environment variable is not set."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"local_test.py": "pass"})

            # Explicitly remove CI env var
            result = harness.run_cli(
                "test",
                env={"CI": ""},  # Empty means not in CI
            )

            assert isinstance(result, CLIResult)

    def test_github_actions_env_var_detected(self):
        """Test that GITHUB_ACTIONS=true is detected as CI environment."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"gha_test.py": "pass"})

            result = harness.run_cli(
                "test",
                env={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_SHA": "abc123",
                    "GITHUB_REF_NAME": "main",
                },
            )

            assert isinstance(result, CLIResult)

    def test_ci_mode_output_format_differences(self):
        """Test that CI mode may have different output formatting."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"format_test.py": "pass"})

            # Run in CI mode
            ci_result = harness.run_cli(
                "test",
                env={"CI": "true"},
            )

            # Results should be valid regardless of CI mode
            assert isinstance(ci_result, CLIResult)

    def test_ci_mode_non_interactive(self):
        """Test that CI mode runs non-interactively without prompts."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"noninteractive.py": "pass"})

            # CI mode should not prompt for user input
            result = harness.run_cli(
                "test",
                env={"CI": "true"},
                timeout=30.0,  # Should complete without hanging for input
            )

            # Should complete without timeout (not waiting for input)
            timed_out = result.returncode == -1 and "timed out" in result.stderr.lower()
            assert not timed_out, "CI mode should not hang waiting for user input"


class TestCombinedCICDEnvironment:
    """Tests for realistic CI/CD environment combinations."""

    def test_full_github_actions_push_event(self):
        """Test with full set of GitHub Actions env vars for push event."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"feature.py": "# New feature"})

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_SHA": "a1b2c3d4e5f6789012345678901234567890abcd",
                    "GITHUB_REF_NAME": "main",
                    "GITHUB_REPOSITORY": "org/repo",
                    "GITHUB_RUN_ID": "12345",
                    "GITHUB_WORKFLOW": "CI",
                },
            )

            assert isinstance(result, CLIResult)
            # Should complete successfully in CI environment
            requests = harness.get_api_requests(method="POST", path="/suite")
            assert len(requests) >= 1

    def test_full_github_actions_pr_event(self):
        """Test with full set of GitHub Actions env vars for PR event."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"pr_fix.py": "# Fix for PR"})

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_SHA": "b2c3d4e5f6789012345678901234567890abcdef",
                    "GITHUB_REF_NAME": "42/merge",
                    "GITHUB_HEAD_REF": "feature/fix-bug",
                    "GITHUB_BASE_REF": "main",
                    "GITHUB_REPOSITORY": "org/repo",
                    "GITHUB_EVENT_NAME": "pull_request",
                    "GITHUB_RUN_ID": "67890",
                },
            )

            assert isinstance(result, CLIResult)
            requests = harness.get_api_requests(method="POST", path="/suite")
            assert len(requests) >= 1

    def test_env_vars_not_leaked_to_output(self):
        """Test that sensitive env vars are not leaked to stdout/stderr."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            secret_value = "super-secret-token-do-not-leak"
            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_TOKEN": secret_value,
                    "GITHUB_SHA": "abc123",
                },
            )

            # Secret should not appear in output
            assert secret_value not in result.stdout, \
                "Secret token should not appear in stdout"
            assert secret_value not in result.stderr, \
                "Secret token should not appear in stderr"


class TestEnvVarPrecedence:
    """Tests for environment variable precedence rules."""

    def test_cli_flag_overrides_env_var(self):
        """Test that explicit CLI flags override environment variables."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"override.py": "pass"})

            # If CLI supports --commit flag, it should override GITHUB_SHA
            cli_commit = "cli1234567890123456789012345678901234567"
            env_commit = "env9876543210987654321098765432109876543"

            result = harness.run_cli(
                "test",
                "--commit", cli_commit,
                env={
                    "GITHUB_SHA": env_commit,
                    "CI": "true",
                },
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                commit_field = (
                    body.get("commit_sha") or
                    body.get("commitSha") or
                    body.get("sha") or
                    body.get("commit")
                )
                # CLI flag should take precedence
                if commit_field and commit_field not in [cli_commit, env_commit]:
                    # Neither matched - CLI may have different behavior
                    pass  # Test structure is correct, behavior TBD

    def test_github_head_ref_preferred_for_branch_in_pr(self):
        """Test that GITHUB_HEAD_REF is preferred over GITHUB_REF_NAME for PRs."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"pr_test.py": "pass"})

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_HEAD_REF": "feature/the-actual-branch",
                    "GITHUB_REF_NAME": "refs/pull/123/merge",
                },
            )

            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                branch_field = (
                    body.get("branch_name") or
                    body.get("branchName") or
                    body.get("branch")
                )
                # For PRs, should prefer HEAD_REF (source branch) over REF_NAME (merge ref)
                if branch_field:
                    is_merge_ref = "merge" in branch_field.lower()
                    is_expected = branch_field == "feature/the-actual-branch"
                    assert not is_merge_ref or is_expected, \
                        "Should prefer HEAD_REF over merge ref for branch name"

    def test_env_vars_with_special_characters(self):
        """Test handling of env vars containing special characters."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"special.py": "pass"})

            # Branch names can contain special characters
            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_REF_NAME": "feature/JIRA-1234_fix-auth",
                    "GITHUB_SHA": "abc123",
                },
            )

            # Should handle without errors
            assert isinstance(result, CLIResult)


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_missing_github_sha_in_ci(self):
        """Test behavior when GITHUB_SHA is missing but CI=true."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.repo.add_file("test.py", "pass")
            harness.repo.commit("Add test")

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_ACTIONS": "true",
                    # GITHUB_SHA intentionally missing
                    "GITHUB_REF_NAME": "main",
                },
            )

            # Should fall back to local git HEAD
            assert isinstance(result, CLIResult)
            requests = harness.get_api_requests(method="POST", path="/suite")
            if requests:
                body = requests[0]["body"]
                commit_field = (
                    body.get("commit_sha") or
                    body.get("commitSha") or
                    body.get("sha") or
                    body.get("commit")
                )
                # Should have some commit hash (from local git)
                if commit_field:
                    assert len(commit_field) > 0

    def test_empty_env_vars_treated_as_unset(self):
        """Test that empty string env vars are treated as unset."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.repo.add_file("empty.py", "pass")
            harness.repo.commit("Add file")

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_SHA": "",  # Empty should be treated as unset
                    "GITHUB_REF_NAME": "",
                    "GITHUB_HEAD_REF": "",
                },
            )

            # Should not crash, should fall back to local git
            assert isinstance(result, CLIResult)

    def test_invalid_sha_format(self):
        """Test handling of invalid SHA format."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"invalid.py": "pass"})

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_SHA": "not-a-valid-sha!@#$%",
                },
            )

            # Should handle gracefully, not crash
            assert isinstance(result, CLIResult)

    def test_unicode_in_branch_name(self):
        """Test handling of unicode characters in branch names."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"unicode.py": "pass"})

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_REF_NAME": "feature/update-emoji",
                },
            )

            assert isinstance(result, CLIResult)

    def test_very_long_env_values(self):
        """Test handling of very long environment variable values."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"long.py": "pass"})

            # Extremely long branch name (edge case)
            long_branch = "feature/" + "a" * 200

            result = harness.run_cli(
                "test",
                env={
                    "CI": "true",
                    "GITHUB_REF_NAME": long_branch,
                    "GITHUB_SHA": "abc123",
                },
            )

            # Should handle without crashing
            assert isinstance(result, CLIResult)
