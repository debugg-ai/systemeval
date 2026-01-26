"""
GitRepoFixture - Temporary git repository management for testing.

Provides a test fixture for creating and managing temporary git repositories
with controlled state, commits, branches, and working directory changes.

Usage:
    from tests.fixtures.git_repo_fixture import GitRepoFixture

    # Create a temporary repo
    with GitRepoFixture() as repo:
        # Add files and commit
        repo.add_file("src/app.py", "print('hello')")
        repo.commit("Initial commit")

        # Create a feature branch
        repo.create_branch("feature-branch")
        repo.modify_file("src/app.py", "print('hello world')")
        repo.commit("Update greeting")

        # Get the repo path for testing
        print(repo.path)  # /tmp/xxx/repo

    # Or use with pytest fixture
    def test_git_analysis(git_repo):
        git_repo.add_file("test.py", "pass")
        git_repo.commit("Add test")
        # ...
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CommitInfo:
    """Information about a commit."""

    hash: str
    message: str
    author: str
    date: str
    files_changed: List[str] = field(default_factory=list)


@dataclass
class FileChange:
    """Represents a file change in the working directory."""

    path: str
    status: str  # added, modified, deleted, renamed
    staged: bool
    old_path: Optional[str] = None  # For renames


class GitRepoFixture:
    """
    Temporary git repository for testing.

    Features:
    - Creates isolated git repo in temp directory
    - Helper methods for common git operations
    - Tracks commits and file changes
    - Automatic cleanup on exit
    - Branch management
    """

    def __init__(
        self,
        initial_branch: str = "main",
        author_name: str = "Test User",
        author_email: str = "test@example.com",
        keep_on_error: bool = False,
    ):
        """
        Initialize the git repo fixture.

        Args:
            initial_branch: Name of the initial branch
            author_name: Git author name for commits
            author_email: Git author email for commits
            keep_on_error: Don't delete repo on error (for debugging)
        """
        self.initial_branch = initial_branch
        self.author_name = author_name
        self.author_email = author_email
        self.keep_on_error = keep_on_error

        # State
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._path: Optional[Path] = None
        self._commits: List[CommitInfo] = []
        self._branches: List[str] = []
        self._current_branch: str = initial_branch
        self._initialized: bool = False

    @property
    def path(self) -> Path:
        """Get the repository path."""
        if self._path is None:
            raise RuntimeError("Repository not initialized. Use start() or context manager.")
        return self._path

    @property
    def commits(self) -> List[CommitInfo]:
        """Get list of commits made in this repo."""
        return self._commits.copy()

    @property
    def branches(self) -> List[str]:
        """Get list of branches."""
        return self._branches.copy()

    @property
    def current_branch(self) -> str:
        """Get current branch name."""
        return self._current_branch

    def start(self) -> "GitRepoFixture":
        """Initialize the temporary repository."""
        if self._initialized:
            return self

        # Create temp directory
        self._temp_dir = tempfile.TemporaryDirectory(prefix="test_git_repo_")
        self._path = Path(self._temp_dir.name)

        # Initialize git repo
        self._run_git("init", "-b", self.initial_branch)

        # Configure git
        self._run_git("config", "user.name", self.author_name)
        self._run_git("config", "user.email", self.author_email)

        # Create initial commit to establish branch
        readme = self._path / "README.md"
        readme.write_text("# Test Repository\n")
        self._run_git("add", "README.md")
        self._run_git("commit", "-m", "Initial commit")

        # Record initial commit
        self._record_last_commit()
        self._branches.append(self.initial_branch)

        self._initialized = True
        return self

    def stop(self, error: bool = False) -> None:
        """Clean up the temporary repository."""
        if self._temp_dir:
            if error and self.keep_on_error:
                print(f"Keeping test repo at: {self._path}")
            else:
                try:
                    self._temp_dir.cleanup()
                except Exception:
                    pass  # Ignore cleanup errors
            self._temp_dir = None
            self._path = None
            self._initialized = False

    # ========================================================================
    # File Operations
    # ========================================================================

    def add_file(
        self,
        path: str,
        content: str,
        stage: bool = True,
    ) -> Path:
        """
        Add a new file to the repository.

        Args:
            path: Relative path for the file
            content: File content
            stage: Whether to stage the file

        Returns:
            Absolute path to the created file
        """
        file_path = self.path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        if stage:
            self._run_git("add", path)

        return file_path

    def modify_file(
        self,
        path: str,
        content: str,
        stage: bool = True,
    ) -> Path:
        """
        Modify an existing file.

        Args:
            path: Relative path to the file
            content: New file content
            stage: Whether to stage the changes

        Returns:
            Absolute path to the modified file
        """
        file_path = self.path / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        file_path.write_text(content)

        if stage:
            self._run_git("add", path)

        return file_path

    def append_to_file(
        self,
        path: str,
        content: str,
        stage: bool = True,
    ) -> Path:
        """
        Append content to an existing file.

        Args:
            path: Relative path to the file
            content: Content to append
            stage: Whether to stage the changes

        Returns:
            Absolute path to the modified file
        """
        file_path = self.path / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(file_path, "a") as f:
            f.write(content)

        if stage:
            self._run_git("add", path)

        return file_path

    def delete_file(
        self,
        path: str,
        stage: bool = True,
    ) -> None:
        """
        Delete a file from the repository.

        Args:
            path: Relative path to the file
            stage: Whether to stage the deletion
        """
        file_path = self.path / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if stage:
            self._run_git("rm", path)
        else:
            file_path.unlink()

    def rename_file(
        self,
        old_path: str,
        new_path: str,
        stage: bool = True,
    ) -> Path:
        """
        Rename/move a file.

        Args:
            old_path: Current relative path
            new_path: New relative path
            stage: Whether to stage the rename

        Returns:
            Absolute path to the new location
        """
        old_file = self.path / old_path
        new_file = self.path / new_path

        if not old_file.exists():
            raise FileNotFoundError(f"File not found: {old_path}")

        new_file.parent.mkdir(parents=True, exist_ok=True)

        if stage:
            self._run_git("mv", old_path, new_path)
        else:
            shutil.move(str(old_file), str(new_file))

        return new_file

    def read_file(self, path: str) -> str:
        """Read a file's content."""
        file_path = self.path / path
        return file_path.read_text()

    def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        return (self.path / path).exists()

    # ========================================================================
    # Git Operations
    # ========================================================================

    def commit(
        self,
        message: str,
        allow_empty: bool = False,
    ) -> CommitInfo:
        """
        Create a commit.

        Args:
            message: Commit message
            allow_empty: Allow empty commits

        Returns:
            CommitInfo for the new commit
        """
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")

        self._run_git(*args)
        return self._record_last_commit()

    def stage_all(self) -> None:
        """Stage all changes."""
        self._run_git("add", "-A")

    def unstage_all(self) -> None:
        """Unstage all staged changes."""
        self._run_git("reset", "HEAD")

    def create_branch(
        self,
        name: str,
        checkout: bool = True,
    ) -> None:
        """
        Create a new branch.

        Args:
            name: Branch name
            checkout: Whether to checkout the branch
        """
        if checkout:
            self._run_git("checkout", "-b", name)
            self._current_branch = name
        else:
            self._run_git("branch", name)

        self._branches.append(name)

    def checkout(self, ref: str) -> None:
        """
        Checkout a branch or commit.

        Args:
            ref: Branch name or commit hash
        """
        self._run_git("checkout", ref)
        if ref in self._branches:
            self._current_branch = ref

    def merge(
        self,
        branch: str,
        message: Optional[str] = None,
        no_ff: bool = False,
    ) -> None:
        """
        Merge a branch into current branch.

        Args:
            branch: Branch to merge
            message: Merge commit message
            no_ff: Force merge commit (no fast-forward)
        """
        args = ["merge", branch]
        if message:
            args.extend(["-m", message])
        if no_ff:
            args.append("--no-ff")

        self._run_git(*args)

    def get_head_commit(self) -> str:
        """Get the HEAD commit hash."""
        result = self._run_git("rev-parse", "HEAD")
        return result.stdout.strip()

    def get_commit_count(self) -> int:
        """Get the number of commits."""
        result = self._run_git("rev-list", "--count", "HEAD")
        return int(result.stdout.strip())

    def get_diff(
        self,
        ref1: Optional[str] = None,
        ref2: Optional[str] = None,
        staged: bool = False,
    ) -> str:
        """
        Get diff output.

        Args:
            ref1: First ref (None for working dir)
            ref2: Second ref
            staged: Show staged changes

        Returns:
            Diff output as string
        """
        args = ["diff"]
        if staged:
            args.append("--cached")
        if ref1:
            args.append(ref1)
        if ref2:
            args.append(ref2)

        result = self._run_git(*args)
        return result.stdout

    def get_status(self) -> List[FileChange]:
        """
        Get working directory status.

        Returns:
            List of FileChange objects
        """
        result = self._run_git("status", "--porcelain")
        changes = []

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            # Parse porcelain output: XY filename
            index_status = line[0]
            worktree_status = line[1]
            path = line[3:].strip()

            # Determine status and staged
            if index_status == "A":
                status = "added"
                staged = True
            elif index_status == "M":
                status = "modified"
                staged = True
            elif index_status == "D":
                status = "deleted"
                staged = True
            elif index_status == "R":
                status = "renamed"
                staged = True
            elif worktree_status == "M":
                status = "modified"
                staged = False
            elif worktree_status == "D":
                status = "deleted"
                staged = False
            elif index_status == "?" and worktree_status == "?":
                status = "added"
                staged = False
            else:
                status = "unknown"
                staged = index_status != " "

            changes.append(FileChange(
                path=path,
                status=status,
                staged=staged,
            ))

        return changes

    def get_log(
        self,
        count: int = 10,
        format_str: str = "%H|%s|%an|%aI",
    ) -> List[CommitInfo]:
        """
        Get commit log.

        Args:
            count: Number of commits to return
            format_str: Git log format string

        Returns:
            List of CommitInfo objects
        """
        result = self._run_git("log", f"-{count}", f"--format={format_str}")
        commits = []

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                commits.append(CommitInfo(
                    hash=parts[0],
                    message=parts[1],
                    author=parts[2],
                    date=parts[3],
                ))

        return commits

    # ========================================================================
    # PR Simulation
    # ========================================================================

    def setup_pr_scenario(
        self,
        base_branch: str = "main",
        head_branch: str = "feature",
        num_commits: int = 3,
    ) -> Tuple[str, str]:
        """
        Set up a PR-like scenario with base and head branches.

        Args:
            base_branch: Name of base branch
            head_branch: Name of feature branch
            num_commits: Number of commits on feature branch

        Returns:
            Tuple of (base_commit_hash, head_commit_hash)
        """
        # Ensure we're on base branch
        if self._current_branch != base_branch:
            if base_branch not in self._branches:
                self.create_branch(base_branch)
            else:
                self.checkout(base_branch)

        base_hash = self.get_head_commit()

        # Create feature branch
        self.create_branch(head_branch)

        # Add commits
        for i in range(1, num_commits + 1):
            filename = f"feature_{i}.py"
            self.add_file(filename, f"# Feature {i}\nprint('feature {i}')\n")
            self.commit(f"Add feature {i}")

        head_hash = self.get_head_commit()

        return base_hash, head_hash

    def get_commits_between(
        self,
        base: str,
        head: str,
    ) -> List[CommitInfo]:
        """
        Get commits between two refs (base..head).

        Args:
            base: Base commit/branch
            head: Head commit/branch

        Returns:
            List of commits
        """
        result = self._run_git(
            "log",
            f"{base}..{head}",
            "--format=%H|%s|%an|%aI",
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                commits.append(CommitInfo(
                    hash=parts[0],
                    message=parts[1],
                    author=parts[2],
                    date=parts[3],
                ))

        return commits

    # ========================================================================
    # Internal Methods
    # ========================================================================

    def _run_git(self, *args: str) -> subprocess.CompletedProcess:
        """Run a git command in the repo."""
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        return result

    def _record_last_commit(self) -> CommitInfo:
        """Record info about the last commit."""
        result = self._run_git("log", "-1", "--format=%H|%s|%an|%aI")
        parts = result.stdout.strip().split("|")

        # Get changed files
        diff_result = self._run_git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
        files = [f for f in diff_result.stdout.strip().split("\n") if f]

        commit = CommitInfo(
            hash=parts[0],
            message=parts[1],
            author=parts[2],
            date=parts[3],
            files_changed=files,
        )
        self._commits.append(commit)
        return commit

    # ========================================================================
    # Context Manager
    # ========================================================================

    def __enter__(self) -> "GitRepoFixture":
        """Context manager entry."""
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop(error=exc_type is not None)


# ============================================================================
# Pytest Fixtures
# ============================================================================


def git_repo_fixture(**kwargs):
    """
    Factory function for creating GitRepoFixture instances.

    Usage in conftest.py:
        @pytest.fixture
        def git_repo():
            with GitRepoFixture() as repo:
                yield repo
    """
    return GitRepoFixture(**kwargs)


def create_git_repo(**kwargs) -> GitRepoFixture:
    """Create and start a git repo fixture."""
    repo = GitRepoFixture(**kwargs)
    return repo.start()
