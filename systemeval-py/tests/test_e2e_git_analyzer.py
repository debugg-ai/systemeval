"""
Tests for E2E git analyzer module.

Tests the git analysis wrapper functionality for generating ChangeSet objects
compatible with E2EProvider.generate_tests().
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from systemeval.e2e.git_analyzer import (
    GitAnalysisError,
    _parse_change_type,
    _parse_numstat_line,
    _run_git_command,
    _validate_repo,
    analyze_commit,
    analyze_pr_changes,
    analyze_range,
    analyze_working_changes,
    get_current_branch,
    get_default_branch,
)
from systemeval.e2e.types import ChangeSet, ChangeType


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository with some commits."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize repo
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create main branch (some git versions default to master)
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_path, capture_output=True, check=True)

    return repo_path


@pytest.fixture
def temp_git_repo_with_changes(temp_git_repo):
    """Create a temp repo with working directory changes."""
    repo_path = temp_git_repo

    # Add a new file (staged)
    new_file = repo_path / "new_file.py"
    new_file.write_text("def hello():\n    return 'world'\n")
    subprocess.run(["git", "add", "new_file.py"], cwd=repo_path, capture_output=True, check=True)

    # Modify existing file (unstaged)
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n\nUpdated content.\n")

    return repo_path


@pytest.fixture
def temp_git_repo_with_branches(temp_git_repo):
    """Create a temp repo with multiple branches."""
    repo_path = temp_git_repo

    # Create feature branch
    subprocess.run(
        ["git", "checkout", "-b", "feature-branch"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Add some changes on feature branch
    feature_file = repo_path / "feature.py"
    feature_file.write_text("# Feature code\n")
    subprocess.run(["git", "add", "feature.py"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add feature"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Add another commit
    feature_file.write_text("# Feature code\ndef feature():\n    pass\n")
    subprocess.run(["git", "add", "feature.py"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Implement feature"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    return repo_path


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestParseChangeType:
    """Test _parse_change_type helper."""

    def test_added(self):
        """Test parsing 'A' status."""
        assert _parse_change_type("A") == ChangeType.ADDED

    def test_modified(self):
        """Test parsing 'M' status."""
        assert _parse_change_type("M") == ChangeType.MODIFIED

    def test_deleted(self):
        """Test parsing 'D' status."""
        assert _parse_change_type("D") == ChangeType.DELETED

    def test_renamed(self):
        """Test parsing 'R' status."""
        assert _parse_change_type("R") == ChangeType.RENAMED

    def test_renamed_with_percentage(self):
        """Test parsing 'R100' status (rename with similarity)."""
        assert _parse_change_type("R100") == ChangeType.RENAMED

    def test_copied(self):
        """Test parsing 'C' status (treated as added)."""
        assert _parse_change_type("C") == ChangeType.ADDED

    def test_type_changed(self):
        """Test parsing 'T' status (treated as modified)."""
        assert _parse_change_type("T") == ChangeType.MODIFIED

    def test_unknown(self):
        """Test parsing unknown status defaults to modified."""
        assert _parse_change_type("X") == ChangeType.MODIFIED

    def test_empty(self):
        """Test parsing empty status defaults to modified."""
        assert _parse_change_type("") == ChangeType.MODIFIED


class TestParseNumstatLine:
    """Test _parse_numstat_line helper."""

    def test_normal_line(self):
        """Test parsing normal numstat line."""
        additions, deletions, filepath = _parse_numstat_line("10\t5\tsrc/main.py")
        assert additions == 10
        assert deletions == 5
        assert filepath == "src/main.py"

    def test_binary_file(self):
        """Test parsing binary file (shows as -)."""
        additions, deletions, filepath = _parse_numstat_line("-\t-\timage.png")
        assert additions == 0
        assert deletions == 0
        assert filepath == "image.png"

    def test_no_deletions(self):
        """Test parsing line with no deletions."""
        additions, deletions, filepath = _parse_numstat_line("50\t0\tnew_file.py")
        assert additions == 50
        assert deletions == 0
        assert filepath == "new_file.py"

    def test_malformed_line(self):
        """Test parsing malformed line returns defaults."""
        additions, deletions, filepath = _parse_numstat_line("invalid")
        assert additions == 0
        assert deletions == 0
        assert filepath == ""


class TestValidateRepo:
    """Test _validate_repo helper."""

    def test_valid_repo(self, temp_git_repo):
        """Test validation passes for valid repo."""
        _validate_repo(temp_git_repo)  # Should not raise

    def test_nonexistent_path(self, tmp_path):
        """Test validation fails for nonexistent path."""
        with pytest.raises(GitAnalysisError) as exc_info:
            _validate_repo(tmp_path / "nonexistent")
        assert "does not exist" in str(exc_info.value)

    def test_file_path(self, tmp_path):
        """Test validation fails for file path."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("not a repo")
        with pytest.raises(GitAnalysisError) as exc_info:
            _validate_repo(file_path)
        assert "not a directory" in str(exc_info.value)

    def test_non_git_directory(self, tmp_path):
        """Test validation fails for non-git directory."""
        with pytest.raises(GitAnalysisError) as exc_info:
            _validate_repo(tmp_path)
        assert "Not a git repository" in str(exc_info.value)


class TestRunGitCommand:
    """Test _run_git_command helper."""

    def test_successful_command(self, temp_git_repo):
        """Test running successful git command."""
        result = _run_git_command(temp_git_repo, ["status"])
        assert result.returncode == 0

    def test_failed_command_with_check(self, temp_git_repo):
        """Test failed command raises with check=True."""
        with pytest.raises(GitAnalysisError) as exc_info:
            _run_git_command(temp_git_repo, ["rev-parse", "--verify", "nonexistent"])
        assert exc_info.value.returncode != 0

    def test_failed_command_without_check(self, temp_git_repo):
        """Test failed command returns result with check=False."""
        result = _run_git_command(
            temp_git_repo, ["rev-parse", "--verify", "nonexistent"], check=False
        )
        assert result.returncode != 0


# ============================================================================
# get_current_branch Tests
# ============================================================================


class TestGetCurrentBranch:
    """Test get_current_branch function."""

    def test_main_branch(self, temp_git_repo):
        """Test getting current branch name on main."""
        branch = get_current_branch(temp_git_repo)
        assert branch == "main"

    def test_feature_branch(self, temp_git_repo_with_branches):
        """Test getting current branch name on feature branch."""
        branch = get_current_branch(temp_git_repo_with_branches)
        assert branch == "feature-branch"

    def test_detached_head(self, temp_git_repo):
        """Test getting commit SHA in detached HEAD state."""
        # Get current commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_sha = result.stdout.strip()

        # Checkout the commit directly (detached HEAD)
        subprocess.run(
            ["git", "checkout", commit_sha],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        branch = get_current_branch(temp_git_repo)
        # Should return short SHA when in detached state
        assert len(branch) >= 7  # Short SHA is at least 7 chars

    def test_invalid_repo(self, tmp_path):
        """Test error on invalid repo."""
        with pytest.raises(GitAnalysisError):
            get_current_branch(tmp_path)


# ============================================================================
# get_default_branch Tests
# ============================================================================


class TestGetDefaultBranch:
    """Test get_default_branch function."""

    def test_main_branch_exists(self, temp_git_repo):
        """Test finding main branch."""
        branch = get_default_branch(temp_git_repo)
        assert branch == "main"

    def test_master_branch_fallback(self, temp_git_repo):
        """Test fallback to master when main doesn't exist."""
        # Rename main to master
        subprocess.run(
            ["git", "branch", "-M", "master"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        branch = get_default_branch(temp_git_repo)
        assert branch == "master"

    def test_no_default_branch(self, temp_git_repo):
        """Test error when neither main nor master exists."""
        # Rename to a non-standard branch
        subprocess.run(
            ["git", "branch", "-M", "development"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        with pytest.raises(GitAnalysisError) as exc_info:
            get_default_branch(temp_git_repo)
        assert "Could not determine default branch" in str(exc_info.value)


# ============================================================================
# analyze_working_changes Tests
# ============================================================================


class TestAnalyzeWorkingChanges:
    """Test analyze_working_changes function."""

    def test_no_changes(self, temp_git_repo):
        """Test analyzing repo with no working changes."""
        changeset = analyze_working_changes(temp_git_repo)

        assert isinstance(changeset, ChangeSet)
        assert changeset.head_ref == "WORKING"
        assert len(changeset.changes) == 0
        assert changeset.repository_root == temp_git_repo.resolve()
        assert changeset.metadata["type"] == "working_changes"

    def test_staged_changes(self, temp_git_repo):
        """Test analyzing staged changes."""
        # Create and stage a new file
        new_file = temp_git_repo / "staged.py"
        new_file.write_text("print('staged')\n")
        subprocess.run(
            ["git", "add", "staged.py"], cwd=temp_git_repo, capture_output=True, check=True
        )

        changeset = analyze_working_changes(temp_git_repo)

        assert len(changeset.changes) == 1
        change = changeset.changes[0]
        assert change.file_path == "staged.py"
        assert change.change_type == ChangeType.ADDED
        assert change.metadata.get("staged") is True

    def test_unstaged_changes(self, temp_git_repo):
        """Test analyzing unstaged changes."""
        # Modify an existing file without staging
        readme = temp_git_repo / "README.md"
        readme.write_text("# Modified\n")

        changeset = analyze_working_changes(temp_git_repo)

        assert len(changeset.changes) == 1
        change = changeset.changes[0]
        assert change.file_path == "README.md"
        assert change.change_type == ChangeType.MODIFIED
        assert change.metadata.get("staged") is False

    def test_mixed_changes(self, temp_git_repo_with_changes):
        """Test analyzing both staged and unstaged changes."""
        changeset = analyze_working_changes(temp_git_repo_with_changes)

        assert len(changeset.changes) == 2

        # Check for staged new file
        staged_change = next(
            (c for c in changeset.changes if c.file_path == "new_file.py"), None
        )
        assert staged_change is not None
        assert staged_change.change_type == ChangeType.ADDED
        assert staged_change.metadata.get("staged") is True

        # Check for unstaged modified file
        unstaged_change = next(
            (c for c in changeset.changes if c.file_path == "README.md"), None
        )
        assert unstaged_change is not None
        assert unstaged_change.change_type == ChangeType.MODIFIED
        assert unstaged_change.metadata.get("staged") is False

    def test_include_diff(self, temp_git_repo_with_changes):
        """Test including diff content in changes."""
        changeset = analyze_working_changes(temp_git_repo_with_changes, include_diff=True)

        # At least one change should have diff content
        changes_with_diff = [c for c in changeset.changes if c.diff]
        assert len(changes_with_diff) >= 1

    def test_staged_only(self, temp_git_repo_with_changes):
        """Test getting only staged changes."""
        changeset = analyze_working_changes(
            temp_git_repo_with_changes, include_staged=True, include_unstaged=False
        )

        # Should only have the staged file
        assert len(changeset.changes) == 1
        assert changeset.changes[0].file_path == "new_file.py"

    def test_unstaged_only(self, temp_git_repo_with_changes):
        """Test getting only unstaged changes."""
        changeset = analyze_working_changes(
            temp_git_repo_with_changes, include_staged=False, include_unstaged=True
        )

        # Should only have the unstaged file
        assert len(changeset.changes) == 1
        assert changeset.changes[0].file_path == "README.md"

    def test_line_counts(self, temp_git_repo):
        """Test that line additions/deletions are counted."""
        # Create a file with known content
        new_file = temp_git_repo / "counted.py"
        new_file.write_text("line1\nline2\nline3\n")
        subprocess.run(
            ["git", "add", "counted.py"], cwd=temp_git_repo, capture_output=True, check=True
        )

        changeset = analyze_working_changes(temp_git_repo)

        change = changeset.changes[0]
        assert change.additions == 3
        assert change.deletions == 0


# ============================================================================
# analyze_commit Tests
# ============================================================================


class TestAnalyzeCommit:
    """Test analyze_commit function."""

    def test_analyze_head_commit(self, temp_git_repo_with_branches):
        """Test analyzing the HEAD commit."""
        changeset = analyze_commit(temp_git_repo_with_branches, "HEAD")

        assert isinstance(changeset, ChangeSet)
        assert len(changeset.head_ref) == 40  # Full SHA
        assert changeset.metadata["type"] == "commit"
        assert "author_name" in changeset.metadata
        assert "subject" in changeset.metadata

    def test_analyze_by_sha(self, temp_git_repo_with_branches):
        """Test analyzing a commit by SHA."""
        # Get the HEAD commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_git_repo_with_branches,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = result.stdout.strip()

        changeset = analyze_commit(temp_git_repo_with_branches, sha)

        assert changeset.head_ref == sha
        assert len(changeset.changes) >= 1

    def test_analyze_short_sha(self, temp_git_repo_with_branches):
        """Test analyzing a commit by short SHA."""
        # Get short SHA
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=temp_git_repo_with_branches,
            capture_output=True,
            text=True,
            check=True,
        )
        short_sha = result.stdout.strip()

        changeset = analyze_commit(temp_git_repo_with_branches, short_sha)

        # head_ref should be the full SHA
        assert len(changeset.head_ref) == 40

    def test_commit_metadata(self, temp_git_repo_with_branches):
        """Test commit metadata is captured."""
        changeset = analyze_commit(temp_git_repo_with_branches, "HEAD")

        assert changeset.metadata["author_name"] == "Test User"
        assert changeset.metadata["author_email"] == "test@test.com"
        assert "Implement feature" in changeset.metadata["subject"]

    def test_include_diff(self, temp_git_repo_with_branches):
        """Test including diff content for commit."""
        changeset = analyze_commit(temp_git_repo_with_branches, "HEAD", include_diff=True)

        # Should have diff content
        changes_with_diff = [c for c in changeset.changes if c.diff]
        assert len(changes_with_diff) >= 1

    def test_nonexistent_commit(self, temp_git_repo):
        """Test error on nonexistent commit."""
        with pytest.raises(GitAnalysisError):
            analyze_commit(temp_git_repo, "abc1234567890")

    def test_initial_commit(self, temp_git_repo):
        """Test analyzing initial commit (no parent)."""
        changeset = analyze_commit(temp_git_repo, "HEAD")

        # Should use empty tree as base
        assert changeset.base_ref == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


# ============================================================================
# analyze_range Tests
# ============================================================================


class TestAnalyzeRange:
    """Test analyze_range function."""

    def test_branch_comparison(self, temp_git_repo_with_branches):
        """Test comparing two branches."""
        changeset = analyze_range(temp_git_repo_with_branches, "main", "feature-branch")

        assert isinstance(changeset, ChangeSet)
        assert changeset.metadata["type"] == "range"
        assert len(changeset.changes) >= 1

        # Should have the feature.py file
        file_paths = [c.file_path for c in changeset.changes]
        assert "feature.py" in file_paths

    def test_commit_range(self, temp_git_repo_with_branches):
        """Test comparing commit SHAs."""
        # Get the last two commit SHAs
        result = subprocess.run(
            ["git", "log", "--format=%H", "-n", "2"],
            cwd=temp_git_repo_with_branches,
            capture_output=True,
            text=True,
            check=True,
        )
        shas = result.stdout.strip().split("\n")
        head_sha = shas[0]
        base_sha = shas[1]

        changeset = analyze_range(temp_git_repo_with_branches, base_sha, head_sha)

        assert changeset.base_ref == base_sha
        assert changeset.head_ref == head_sha

    def test_original_refs_preserved(self, temp_git_repo_with_branches):
        """Test original ref names are preserved in metadata."""
        changeset = analyze_range(temp_git_repo_with_branches, "main", "feature-branch")

        assert changeset.metadata["original_base_ref"] == "main"
        assert changeset.metadata["original_head_ref"] == "feature-branch"

    def test_merge_base_captured(self, temp_git_repo_with_branches):
        """Test merge base is captured in metadata."""
        changeset = analyze_range(temp_git_repo_with_branches, "main", "feature-branch")

        assert "merge_base" in changeset.metadata
        # Merge base should be a valid SHA
        assert changeset.metadata["merge_base"] is not None

    def test_include_diff(self, temp_git_repo_with_branches):
        """Test including diff content in range analysis."""
        changeset = analyze_range(
            temp_git_repo_with_branches, "main", "feature-branch", include_diff=True
        )

        changes_with_diff = [c for c in changeset.changes if c.diff]
        assert len(changes_with_diff) >= 1

    def test_line_counts(self, temp_git_repo_with_branches):
        """Test line additions/deletions in range."""
        changeset = analyze_range(temp_git_repo_with_branches, "main", "feature-branch")

        # feature.py should have additions
        feature_change = next(
            (c for c in changeset.changes if c.file_path == "feature.py"), None
        )
        assert feature_change is not None
        assert feature_change.additions > 0

    def test_invalid_base_ref(self, temp_git_repo):
        """Test error on invalid base ref."""
        with pytest.raises(GitAnalysisError):
            analyze_range(temp_git_repo, "nonexistent", "main")

    def test_invalid_head_ref(self, temp_git_repo):
        """Test error on invalid head ref."""
        with pytest.raises(GitAnalysisError):
            analyze_range(temp_git_repo, "main", "nonexistent")


# ============================================================================
# analyze_pr_changes Tests
# ============================================================================


class TestAnalyzePrChanges:
    """Test analyze_pr_changes convenience function."""

    def test_default_branches(self, temp_git_repo_with_branches):
        """Test using default branches (main -> current)."""
        changeset = analyze_pr_changes(temp_git_repo_with_branches)

        assert changeset.metadata["type"] == "pull_request"
        assert changeset.metadata["base_branch"] == "main"
        assert changeset.metadata["head_branch"] == "feature-branch"

    def test_explicit_branches(self, temp_git_repo_with_branches):
        """Test specifying explicit branches."""
        changeset = analyze_pr_changes(
            temp_git_repo_with_branches,
            base_branch="main",
            head_branch="feature-branch",
        )

        assert changeset.metadata["base_branch"] == "main"
        assert changeset.metadata["head_branch"] == "feature-branch"
        assert len(changeset.changes) >= 1

    def test_include_diff(self, temp_git_repo_with_branches):
        """Test including diff in PR analysis."""
        changeset = analyze_pr_changes(temp_git_repo_with_branches, include_diff=True)

        changes_with_diff = [c for c in changeset.changes if c.diff]
        assert len(changes_with_diff) >= 1


# ============================================================================
# ChangeSet Compatibility Tests
# ============================================================================


class TestChangeSetCompatibility:
    """Test that generated ChangeSets are compatible with E2E types."""

    def test_changeset_has_required_fields(self, temp_git_repo_with_changes):
        """Test ChangeSet has all required fields."""
        changeset = analyze_working_changes(temp_git_repo_with_changes)

        assert hasattr(changeset, "base_ref")
        assert hasattr(changeset, "head_ref")
        assert hasattr(changeset, "changes")
        assert hasattr(changeset, "repository_root")
        assert hasattr(changeset, "timestamp")
        assert hasattr(changeset, "metadata")

    def test_changeset_properties_work(self, temp_git_repo_with_changes):
        """Test ChangeSet computed properties work."""
        changeset = analyze_working_changes(temp_git_repo_with_changes)

        assert isinstance(changeset.total_changes, int)
        assert isinstance(changeset.total_additions, int)
        assert isinstance(changeset.total_deletions, int)

    def test_changeset_to_dict(self, temp_git_repo_with_changes):
        """Test ChangeSet can be serialized."""
        changeset = analyze_working_changes(temp_git_repo_with_changes)

        data = changeset.to_dict()

        assert "base_ref" in data
        assert "head_ref" in data
        assert "changes" in data
        assert "repository_root" in data

    def test_change_has_required_fields(self, temp_git_repo_with_changes):
        """Test Change objects have all required fields."""
        changeset = analyze_working_changes(temp_git_repo_with_changes)

        for change in changeset.changes:
            assert hasattr(change, "file_path")
            assert hasattr(change, "change_type")
            assert hasattr(change, "additions")
            assert hasattr(change, "deletions")
            assert hasattr(change, "diff")
            assert hasattr(change, "metadata")

    def test_get_changes_by_type(self, temp_git_repo_with_changes):
        """Test filtering changes by type."""
        changeset = analyze_working_changes(temp_git_repo_with_changes)

        added = changeset.get_changes_by_type(ChangeType.ADDED)
        modified = changeset.get_changes_by_type(ChangeType.MODIFIED)

        assert len(added) == 1
        assert len(modified) == 1


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling in git analyzer."""

    def test_git_analysis_error_attributes(self):
        """Test GitAnalysisError has expected attributes."""
        error = GitAnalysisError("Test error", command="git status", returncode=1)

        assert str(error) == "Test error"
        assert error.command == "git status"
        assert error.returncode == 1

    def test_invalid_repo_path(self, tmp_path):
        """Test all functions raise on invalid repo."""
        invalid_path = tmp_path / "not_a_repo"
        invalid_path.mkdir()

        with pytest.raises(GitAnalysisError):
            get_current_branch(invalid_path)

        with pytest.raises(GitAnalysisError):
            get_default_branch(invalid_path)

        with pytest.raises(GitAnalysisError):
            analyze_working_changes(invalid_path)

        with pytest.raises(GitAnalysisError):
            analyze_commit(invalid_path, "HEAD")

        with pytest.raises(GitAnalysisError):
            analyze_range(invalid_path, "main", "HEAD")

    def test_nonexistent_path(self, tmp_path):
        """Test all functions raise on nonexistent path."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(GitAnalysisError):
            get_current_branch(nonexistent)

        with pytest.raises(GitAnalysisError):
            analyze_working_changes(nonexistent)


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases in git analysis."""

    def test_renamed_file(self, temp_git_repo):
        """Test handling renamed files."""
        # Create and commit a file
        original = temp_git_repo / "original.py"
        original.write_text("content\n")
        subprocess.run(
            ["git", "add", "original.py"], cwd=temp_git_repo, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add original"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Rename the file
        subprocess.run(
            ["git", "mv", "original.py", "renamed.py"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        changeset = analyze_working_changes(temp_git_repo)

        assert len(changeset.changes) == 1
        change = changeset.changes[0]
        assert change.change_type == ChangeType.RENAMED
        assert change.file_path == "renamed.py"
        assert change.old_path == "original.py"

    def test_deleted_file(self, temp_git_repo):
        """Test handling deleted files."""
        # Create and commit a file
        to_delete = temp_git_repo / "to_delete.py"
        to_delete.write_text("content\n")
        subprocess.run(
            ["git", "add", "to_delete.py"], cwd=temp_git_repo, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add file to delete"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Delete the file
        subprocess.run(
            ["git", "rm", "to_delete.py"], cwd=temp_git_repo, capture_output=True, check=True
        )

        changeset = analyze_working_changes(temp_git_repo)

        assert len(changeset.changes) == 1
        change = changeset.changes[0]
        assert change.change_type == ChangeType.DELETED
        assert change.file_path == "to_delete.py"

    def test_binary_file(self, temp_git_repo):
        """Test handling binary files."""
        # Create a binary file
        binary = temp_git_repo / "image.png"
        binary.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        subprocess.run(
            ["git", "add", "image.png"], cwd=temp_git_repo, capture_output=True, check=True
        )

        changeset = analyze_working_changes(temp_git_repo)

        assert len(changeset.changes) == 1
        change = changeset.changes[0]
        assert change.file_path == "image.png"
        # Binary files show 0 lines
        assert change.additions == 0
        assert change.deletions == 0

    def test_file_with_spaces_in_path(self, temp_git_repo):
        """Test handling files with spaces in path."""
        # Create a file with spaces in name
        spaced_dir = temp_git_repo / "path with spaces"
        spaced_dir.mkdir()
        spaced_file = spaced_dir / "file name.py"
        spaced_file.write_text("content\n")
        subprocess.run(
            ["git", "add", str(spaced_file.relative_to(temp_git_repo))],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        changeset = analyze_working_changes(temp_git_repo)

        assert len(changeset.changes) == 1
        assert "path with spaces" in changeset.changes[0].file_path

    def test_empty_repo(self, tmp_path):
        """Test handling repo with no commits."""
        repo_path = tmp_path / "empty_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)

        # An empty repo with no commits will fail when trying to get current branch
        # because HEAD doesn't exist yet. This is expected behavior.
        with pytest.raises(GitAnalysisError) as exc_info:
            get_current_branch(repo_path)
        assert "HEAD" in str(exc_info.value) or "revision" in str(exc_info.value)

    def test_repository_root_is_absolute(self, temp_git_repo):
        """Test that repository_root is always absolute."""
        changeset = analyze_working_changes(temp_git_repo)

        assert changeset.repository_root.is_absolute()

    def test_relative_path_resolved(self, temp_git_repo):
        """Test that relative paths are resolved to absolute."""
        # Get relative path
        relative_path = Path(".")

        # This should work with current directory being the repo
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_git_repo)
            changeset = analyze_working_changes(relative_path)
            assert changeset.repository_root.is_absolute()
        finally:
            os.chdir(original_cwd)
