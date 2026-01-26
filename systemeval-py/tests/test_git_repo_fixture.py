"""Tests for GitRepoFixture fixture."""

import os
import pytest
from pathlib import Path

from tests.fixtures.git_repo_fixture import (
    GitRepoFixture,
    CommitInfo,
    FileChange,
    create_git_repo,
)


class TestGitRepoFixtureBasics:
    """Basic functionality tests for GitRepoFixture."""

    def test_repo_starts_and_stops(self):
        """Test repo starts and stops cleanly."""
        repo = GitRepoFixture()
        repo.start()
        assert repo.path.exists()
        assert (repo.path / ".git").exists()
        path = repo.path  # Store before stop
        repo.stop()
        assert not path.exists()

    def test_context_manager(self):
        """Test repo works as context manager."""
        with GitRepoFixture() as repo:
            assert repo.path.exists()
            assert (repo.path / ".git").exists()
        # After exit, temp dir should be cleaned up

    def test_initial_branch_name(self):
        """Test custom initial branch name."""
        with GitRepoFixture(initial_branch="develop") as repo:
            assert repo.current_branch == "develop"

    def test_initial_commit_created(self):
        """Test that an initial commit is created."""
        with GitRepoFixture() as repo:
            assert repo.get_commit_count() >= 1
            assert (repo.path / "README.md").exists()

    def test_create_git_repo_helper(self):
        """Test create_git_repo helper function."""
        repo = create_git_repo(initial_branch="test-branch")
        try:
            assert repo.path.exists()
            assert repo.current_branch == "test-branch"
        finally:
            repo.stop()


class TestFileOperations:
    """Tests for file operations."""

    def test_add_file(self):
        """Test adding a new file."""
        with GitRepoFixture() as repo:
            file_path = repo.add_file("src/app.py", "print('hello')")
            assert file_path.exists()
            assert file_path.read_text() == "print('hello')"

    def test_add_file_creates_directories(self):
        """Test that add_file creates parent directories."""
        with GitRepoFixture() as repo:
            file_path = repo.add_file("deep/nested/path/file.txt", "content")
            assert file_path.exists()
            assert file_path.parent.exists()

    def test_add_file_staged_by_default(self):
        """Test that add_file stages the file by default."""
        with GitRepoFixture() as repo:
            repo.add_file("new_file.txt", "content")
            status = repo.get_status()
            staged_files = [f for f in status if f.staged and f.status == "added"]
            assert any(f.path == "new_file.txt" for f in staged_files)

    def test_add_file_unstaged(self):
        """Test adding a file without staging."""
        with GitRepoFixture() as repo:
            repo.add_file("untracked.txt", "content", stage=False)
            status = repo.get_status()
            unstaged_files = [f for f in status if not f.staged]
            assert any(f.path == "untracked.txt" for f in unstaged_files)

    def test_modify_file(self):
        """Test modifying an existing file."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "original")
            repo.commit("Add file")

            repo.modify_file("file.txt", "modified")
            assert repo.read_file("file.txt") == "modified"

    def test_modify_nonexistent_file_raises(self):
        """Test that modifying a nonexistent file raises."""
        with GitRepoFixture() as repo:
            with pytest.raises(FileNotFoundError):
                repo.modify_file("nonexistent.txt", "content")

    def test_append_to_file(self):
        """Test appending to an existing file."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "line1\n")
            repo.commit("Add file")

            repo.append_to_file("file.txt", "line2\n")
            content = repo.read_file("file.txt")
            assert content == "line1\nline2\n"

    def test_delete_file(self):
        """Test deleting a file."""
        with GitRepoFixture() as repo:
            repo.add_file("to_delete.txt", "content")
            repo.commit("Add file")

            repo.delete_file("to_delete.txt")
            assert not repo.file_exists("to_delete.txt")

    def test_delete_nonexistent_file_raises(self):
        """Test that deleting a nonexistent file raises."""
        with GitRepoFixture() as repo:
            with pytest.raises(FileNotFoundError):
                repo.delete_file("nonexistent.txt")

    def test_rename_file(self):
        """Test renaming a file."""
        with GitRepoFixture() as repo:
            repo.add_file("old_name.txt", "content")
            repo.commit("Add file")

            new_path = repo.rename_file("old_name.txt", "new_name.txt")
            assert new_path.exists()
            assert not repo.file_exists("old_name.txt")
            assert repo.file_exists("new_name.txt")

    def test_rename_to_new_directory(self):
        """Test renaming a file to a new directory."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "content")
            repo.commit("Add file")

            new_path = repo.rename_file("file.txt", "subdir/file.txt")
            assert new_path.exists()
            assert repo.file_exists("subdir/file.txt")

    def test_read_file(self):
        """Test reading a file's content."""
        with GitRepoFixture() as repo:
            repo.add_file("test.txt", "test content")
            assert repo.read_file("test.txt") == "test content"

    def test_file_exists(self):
        """Test file existence check."""
        with GitRepoFixture() as repo:
            assert not repo.file_exists("nonexistent.txt")
            repo.add_file("exists.txt", "content")
            assert repo.file_exists("exists.txt")


class TestGitOperations:
    """Tests for git operations."""

    def test_commit(self):
        """Test creating a commit."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "content")
            commit = repo.commit("Test commit")

            assert isinstance(commit, CommitInfo)
            assert commit.message == "Test commit"
            assert len(commit.hash) == 40
            assert "file.txt" in commit.files_changed

    def test_commit_allow_empty(self):
        """Test creating an empty commit."""
        with GitRepoFixture() as repo:
            initial_count = repo.get_commit_count()
            repo.commit("Empty commit", allow_empty=True)
            assert repo.get_commit_count() == initial_count + 1

    def test_stage_all(self):
        """Test staging all changes."""
        with GitRepoFixture() as repo:
            repo.add_file("file1.txt", "content", stage=False)
            repo.add_file("file2.txt", "content", stage=False)

            repo.stage_all()

            status = repo.get_status()
            staged = [f for f in status if f.staged]
            assert len(staged) >= 2

    def test_unstage_all(self):
        """Test unstaging all changes."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "content")
            repo.unstage_all()

            status = repo.get_status()
            unstaged = [f for f in status if not f.staged and f.path == "file.txt"]
            assert len(unstaged) == 1

    def test_create_branch(self):
        """Test creating a new branch."""
        with GitRepoFixture() as repo:
            repo.create_branch("feature-branch")
            assert repo.current_branch == "feature-branch"
            assert "feature-branch" in repo.branches

    def test_create_branch_without_checkout(self):
        """Test creating a branch without checking it out."""
        with GitRepoFixture() as repo:
            original_branch = repo.current_branch
            repo.create_branch("other-branch", checkout=False)
            assert repo.current_branch == original_branch
            assert "other-branch" in repo.branches

    def test_checkout_branch(self):
        """Test checking out a branch."""
        with GitRepoFixture() as repo:
            repo.create_branch("branch-a")
            repo.create_branch("branch-b")

            repo.checkout("branch-a")
            assert repo.current_branch == "branch-a"

    def test_checkout_commit(self):
        """Test checking out a specific commit."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "version 1")
            commit1 = repo.commit("First")

            repo.add_file("file2.txt", "version 2")
            repo.commit("Second")

            repo.checkout(commit1.hash)
            # Should be in detached HEAD state
            assert not repo.file_exists("file2.txt")

    def test_merge(self):
        """Test merging branches."""
        with GitRepoFixture() as repo:
            # Add file on main
            repo.add_file("main_file.txt", "from main")
            repo.commit("Main commit")

            # Create feature branch and add file
            repo.create_branch("feature")
            repo.add_file("feature_file.txt", "from feature")
            repo.commit("Feature commit")

            # Merge back to main
            repo.checkout("main")
            repo.merge("feature")

            assert repo.file_exists("feature_file.txt")

    def test_get_head_commit(self):
        """Test getting HEAD commit hash."""
        with GitRepoFixture() as repo:
            head = repo.get_head_commit()
            assert len(head) == 40
            assert all(c in "0123456789abcdef" for c in head)

    def test_get_commit_count(self):
        """Test getting commit count."""
        with GitRepoFixture() as repo:
            initial_count = repo.get_commit_count()

            repo.add_file("file.txt", "content")
            repo.commit("New commit")

            assert repo.get_commit_count() == initial_count + 1

    def test_get_diff_staged(self):
        """Test getting staged diff."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "content")
            repo.commit("Add file")

            repo.modify_file("file.txt", "new content")
            diff = repo.get_diff(staged=True)

            assert "new content" in diff

    def test_get_diff_between_refs(self):
        """Test getting diff between two refs."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "version 1")
            commit1 = repo.commit("First")

            repo.modify_file("file.txt", "version 2")
            commit2 = repo.commit("Second")

            diff = repo.get_diff(commit1.hash, commit2.hash)
            assert "version 2" in diff

    def test_get_status(self):
        """Test getting working directory status."""
        with GitRepoFixture() as repo:
            repo.add_file("staged.txt", "content")
            repo.add_file("unstaged.txt", "content", stage=False)

            status = repo.get_status()

            staged_files = [f for f in status if f.staged]
            unstaged_files = [f for f in status if not f.staged]

            assert any(f.path == "staged.txt" for f in staged_files)
            assert any(f.path == "unstaged.txt" for f in unstaged_files)

    def test_get_log(self):
        """Test getting commit log."""
        with GitRepoFixture() as repo:
            repo.add_file("file1.txt", "content")
            repo.commit("Commit 1")

            repo.add_file("file2.txt", "content")
            repo.commit("Commit 2")

            log = repo.get_log(count=3)
            assert len(log) >= 2
            assert all(isinstance(c, CommitInfo) for c in log)
            assert log[0].message == "Commit 2"
            assert log[1].message == "Commit 1"


class TestPRScenario:
    """Tests for PR simulation functionality."""

    def test_setup_pr_scenario(self):
        """Test setting up a PR-like scenario."""
        with GitRepoFixture() as repo:
            base_hash, head_hash = repo.setup_pr_scenario(
                base_branch="main",
                head_branch="feature",
                num_commits=3,
            )

            assert len(base_hash) == 40
            assert len(head_hash) == 40
            assert base_hash != head_hash
            assert repo.current_branch == "feature"

    def test_setup_pr_scenario_creates_files(self):
        """Test that PR scenario creates feature files."""
        with GitRepoFixture() as repo:
            repo.setup_pr_scenario(num_commits=2)

            assert repo.file_exists("feature_1.py")
            assert repo.file_exists("feature_2.py")

    def test_get_commits_between(self):
        """Test getting commits between two refs."""
        with GitRepoFixture() as repo:
            base_hash, head_hash = repo.setup_pr_scenario(num_commits=3)

            commits = repo.get_commits_between(base_hash, head_hash)

            assert len(commits) == 3
            assert all(isinstance(c, CommitInfo) for c in commits)
            # Commits are in reverse chronological order
            assert "feature 3" in commits[0].message.lower()
            assert "feature 1" in commits[2].message.lower()


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_commit_info_fields(self):
        """Test CommitInfo has all expected fields."""
        with GitRepoFixture() as repo:
            repo.add_file("test.txt", "content")
            commit = repo.commit("Test message")

            assert commit.hash is not None
            assert commit.message == "Test message"
            assert commit.author == "Test User"
            assert commit.date is not None
            assert isinstance(commit.files_changed, list)


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_file_change_added(self):
        """Test FileChange for added files."""
        with GitRepoFixture() as repo:
            repo.add_file("new.txt", "content")

            status = repo.get_status()
            added = [f for f in status if f.path == "new.txt"][0]

            assert added.status == "added"
            assert added.staged is True

    def test_file_change_modified(self):
        """Test FileChange for modified files."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "original")
            repo.commit("Add file")

            repo.modify_file("file.txt", "modified")

            status = repo.get_status()
            modified = [f for f in status if f.path == "file.txt"][0]

            assert modified.status == "modified"
            assert modified.staged is True

    def test_file_change_deleted(self):
        """Test FileChange for deleted files."""
        with GitRepoFixture() as repo:
            repo.add_file("file.txt", "content")
            repo.commit("Add file")

            repo.delete_file("file.txt")

            status = repo.get_status()
            deleted = [f for f in status if f.path == "file.txt"][0]

            assert deleted.status == "deleted"
            assert deleted.staged is True


class TestCommitsProperty:
    """Tests for the commits property."""

    def test_commits_tracks_all_commits(self):
        """Test that commits property tracks all made commits."""
        with GitRepoFixture() as repo:
            # Initial commit is tracked
            initial_commits = len(repo.commits)
            assert initial_commits >= 1

            repo.add_file("file1.txt", "content")
            repo.commit("Commit 1")

            repo.add_file("file2.txt", "content")
            repo.commit("Commit 2")

            assert len(repo.commits) == initial_commits + 2

    def test_commits_returns_copy(self):
        """Test that commits returns a copy."""
        with GitRepoFixture() as repo:
            commits1 = repo.commits
            commits2 = repo.commits
            assert commits1 is not commits2


class TestBranchesProperty:
    """Tests for the branches property."""

    def test_branches_includes_initial(self):
        """Test that branches includes the initial branch."""
        with GitRepoFixture(initial_branch="main") as repo:
            assert "main" in repo.branches

    def test_branches_tracks_new_branches(self):
        """Test that branches tracks newly created branches."""
        with GitRepoFixture() as repo:
            repo.create_branch("feature-1")
            repo.create_branch("feature-2", checkout=False)

            assert "feature-1" in repo.branches
            assert "feature-2" in repo.branches

    def test_branches_returns_copy(self):
        """Test that branches returns a copy."""
        with GitRepoFixture() as repo:
            branches1 = repo.branches
            branches2 = repo.branches
            assert branches1 is not branches2
