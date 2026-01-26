"""
Git analysis wrapper for E2E test generation.

This module provides functions to analyze git repositories and return
ChangeSet objects compatible with E2EProvider.generate_tests().

Uses subprocess to call git commands directly - no external dependencies.
"""

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from ..core.types import Change, ChangeSet, ChangeType


class GitAnalysisError(Exception):
    """Raised when git analysis fails."""

    def __init__(self, message: str, command: Optional[str] = None, returncode: Optional[int] = None):
        super().__init__(message)
        self.command = command
        self.returncode = returncode


def _run_git_command(
    repo_path: Path,
    args: List[str],
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a git command in the specified repository.

    Args:
        repo_path: Path to the git repository
        args: Git command arguments (without 'git' prefix)
        check: Whether to raise on non-zero exit code

    Returns:
        CompletedProcess with stdout/stderr

    Raises:
        GitAnalysisError: If command fails and check=True
    """
    cmd = ["git", "-C", str(repo_path)] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if check and result.returncode != 0:
            raise GitAnalysisError(
                f"Git command failed: {result.stderr.strip() or result.stdout.strip()}",
                command=" ".join(cmd),
                returncode=result.returncode,
            )

        return result

    except subprocess.TimeoutExpired:
        raise GitAnalysisError(
            f"Git command timed out after 60 seconds",
            command=" ".join(cmd),
        )
    except FileNotFoundError:
        raise GitAnalysisError(
            "Git is not installed or not in PATH",
            command=" ".join(cmd),
        )


def _validate_repo(repo_path: Path) -> None:
    """
    Validate that repo_path is a valid git repository.

    Args:
        repo_path: Path to validate

    Raises:
        GitAnalysisError: If not a valid git repository
    """
    if not repo_path.exists():
        raise GitAnalysisError(f"Repository path does not exist: {repo_path}")

    if not repo_path.is_dir():
        raise GitAnalysisError(f"Repository path is not a directory: {repo_path}")

    # Check if it's a git repo
    result = _run_git_command(repo_path, ["rev-parse", "--git-dir"], check=False)
    if result.returncode != 0:
        raise GitAnalysisError(
            f"Not a git repository: {repo_path}",
            command="git rev-parse --git-dir",
            returncode=result.returncode,
        )


def _parse_change_type(status_char: str) -> ChangeType:
    """
    Parse git status character to ChangeType.

    Args:
        status_char: Single character status from git (A, M, D, R, etc.)

    Returns:
        Corresponding ChangeType
    """
    status_map = {
        "A": ChangeType.ADDED,
        "M": ChangeType.MODIFIED,
        "D": ChangeType.DELETED,
        "R": ChangeType.RENAMED,
        "C": ChangeType.ADDED,  # Copied -> treat as added
        "T": ChangeType.MODIFIED,  # Type changed -> treat as modified
        "U": ChangeType.MODIFIED,  # Unmerged -> treat as modified
    }
    # Handle status chars like R100 (rename with percentage)
    base_char = status_char[0] if status_char else "M"
    return status_map.get(base_char, ChangeType.MODIFIED)


def _parse_numstat_line(line: str) -> Tuple[int, int, str]:
    """
    Parse a line from git diff --numstat output.

    Args:
        line: Line in format "additions\tdeletions\tfilepath"

    Returns:
        Tuple of (additions, deletions, filepath)
    """
    parts = line.split("\t")
    if len(parts) >= 3:
        add_str = parts[0]
        del_str = parts[1]
        filepath = parts[2]

        # Binary files show as "-"
        additions = int(add_str) if add_str != "-" else 0
        deletions = int(del_str) if del_str != "-" else 0

        return additions, deletions, filepath

    return 0, 0, ""


def _parse_diff_output(
    repo_path: Path,
    name_status_output: str,
    numstat_output: str,
    diff_output: Optional[str] = None,
) -> List[Change]:
    """
    Parse combined git diff output into Change objects.

    Args:
        repo_path: Repository path for context
        name_status_output: Output from git diff --name-status
        numstat_output: Output from git diff --numstat
        diff_output: Optional full diff output

    Returns:
        List of Change objects
    """
    changes: List[Change] = []

    # Build numstat lookup: filepath -> (additions, deletions)
    numstat_map = {}
    for line in numstat_output.strip().split("\n"):
        if not line:
            continue
        additions, deletions, filepath = _parse_numstat_line(line)
        if filepath:
            numstat_map[filepath] = (additions, deletions)

    # Build diff lookup if provided: filepath -> diff_content
    diff_map = {}
    if diff_output:
        current_file = None
        current_diff_lines = []

        for line in diff_output.split("\n"):
            if line.startswith("diff --git "):
                # Save previous file's diff
                if current_file and current_diff_lines:
                    diff_map[current_file] = "\n".join(current_diff_lines)
                # Extract new filename (after b/)
                match = re.search(r" b/(.+)$", line)
                if match:
                    current_file = match.group(1)
                    current_diff_lines = [line]
            elif current_file:
                current_diff_lines.append(line)

        # Don't forget the last file
        if current_file and current_diff_lines:
            diff_map[current_file] = "\n".join(current_diff_lines)

    # Parse name-status output
    for line in name_status_output.strip().split("\n"):
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        status = parts[0]
        change_type = _parse_change_type(status)

        if change_type == ChangeType.RENAMED and len(parts) >= 3:
            # Renamed: status\told_path\tnew_path
            old_path = parts[1]
            file_path = parts[2]
        else:
            old_path = None
            file_path = parts[1]

        # Get line stats from numstat
        additions, deletions = numstat_map.get(file_path, (0, 0))

        # Get diff content if available
        diff_content = diff_map.get(file_path)

        change = Change(
            file_path=file_path,
            change_type=change_type,
            old_path=old_path,
            additions=additions,
            deletions=deletions,
            diff=diff_content,
        )
        changes.append(change)

    return changes


def get_current_branch(repo_path: Path) -> str:
    """
    Get the current branch name.

    Args:
        repo_path: Path to the git repository

    Returns:
        Current branch name (e.g., "main", "feature-branch")

    Raises:
        GitAnalysisError: If not in a git repo or in detached HEAD state
    """
    _validate_repo(repo_path)

    result = _run_git_command(
        repo_path,
        ["rev-parse", "--abbrev-ref", "HEAD"],
    )

    branch = result.stdout.strip()

    if branch == "HEAD":
        # Detached HEAD state - return the commit SHA instead
        result = _run_git_command(repo_path, ["rev-parse", "--short", "HEAD"])
        return result.stdout.strip()

    return branch


def get_default_branch(repo_path: Path) -> str:
    """
    Get the default branch name (main or master).

    Args:
        repo_path: Path to the git repository

    Returns:
        Default branch name ("main" or "master")

    Raises:
        GitAnalysisError: If neither main nor master exists
    """
    _validate_repo(repo_path)

    # Try to find the default branch from remote
    result = _run_git_command(
        repo_path,
        ["symbolic-ref", "refs/remotes/origin/HEAD"],
        check=False,
    )

    if result.returncode == 0:
        # Extract branch name from refs/remotes/origin/main
        ref = result.stdout.strip()
        if ref:
            return ref.split("/")[-1]

    # Fall back to checking if main or master exist locally
    for branch in ["main", "master"]:
        result = _run_git_command(
            repo_path,
            ["rev-parse", "--verify", branch],
            check=False,
        )
        if result.returncode == 0:
            return branch

    # Check remote branches
    for branch in ["origin/main", "origin/master"]:
        result = _run_git_command(
            repo_path,
            ["rev-parse", "--verify", branch],
            check=False,
        )
        if result.returncode == 0:
            return branch.split("/")[-1]

    raise GitAnalysisError(
        "Could not determine default branch. Neither 'main' nor 'master' found."
    )


def analyze_working_changes(
    repo_path: Path,
    include_staged: bool = True,
    include_unstaged: bool = True,
    include_diff: bool = False,
) -> ChangeSet:
    """
    Get uncommitted changes in the working directory.

    This includes both staged and unstaged changes by default.

    Args:
        repo_path: Path to the git repository
        include_staged: Include staged changes
        include_unstaged: Include unstaged changes
        include_diff: Include full diff content in Change objects

    Returns:
        ChangeSet with all uncommitted changes

    Raises:
        GitAnalysisError: If not a valid git repo
    """
    repo_path = repo_path.resolve()
    _validate_repo(repo_path)

    changes: List[Change] = []

    # Get staged changes (index vs HEAD)
    if include_staged:
        result_status = _run_git_command(
            repo_path,
            ["diff", "--cached", "--name-status"],
        )
        result_numstat = _run_git_command(
            repo_path,
            ["diff", "--cached", "--numstat"],
        )
        diff_output = None
        if include_diff:
            result_diff = _run_git_command(
                repo_path,
                ["diff", "--cached"],
            )
            diff_output = result_diff.stdout

        staged_changes = _parse_diff_output(
            repo_path,
            result_status.stdout,
            result_numstat.stdout,
            diff_output,
        )
        # Mark as staged in metadata
        for change in staged_changes:
            change.metadata["staged"] = True
        changes.extend(staged_changes)

    # Get unstaged changes (working tree vs index)
    if include_unstaged:
        result_status = _run_git_command(
            repo_path,
            ["diff", "--name-status"],
        )
        result_numstat = _run_git_command(
            repo_path,
            ["diff", "--numstat"],
        )
        diff_output = None
        if include_diff:
            result_diff = _run_git_command(
                repo_path,
                ["diff"],
            )
            diff_output = result_diff.stdout

        unstaged_changes = _parse_diff_output(
            repo_path,
            result_status.stdout,
            result_numstat.stdout,
            diff_output,
        )
        # Mark as unstaged in metadata
        for change in unstaged_changes:
            change.metadata["staged"] = False

        # Merge with staged changes, avoiding duplicates
        staged_paths = {c.file_path for c in changes}
        for change in unstaged_changes:
            if change.file_path not in staged_paths:
                changes.append(change)
            else:
                # File has both staged and unstaged changes - update metadata
                for staged_change in changes:
                    if staged_change.file_path == change.file_path:
                        staged_change.metadata["has_unstaged"] = True
                        # Add unstaged line counts
                        staged_change.additions += change.additions
                        staged_change.deletions += change.deletions
                        break

    # Get current HEAD for base_ref
    head_result = _run_git_command(repo_path, ["rev-parse", "HEAD"])
    head_sha = head_result.stdout.strip()

    return ChangeSet(
        base_ref=head_sha,
        head_ref="WORKING",  # Special marker for working directory
        changes=changes,
        repository_root=repo_path,
        metadata={
            "type": "working_changes",
            "include_staged": include_staged,
            "include_unstaged": include_unstaged,
        },
    )


def analyze_commit(
    repo_path: Path,
    commit_sha: str,
    include_diff: bool = False,
) -> ChangeSet:
    """
    Analyze changes introduced by a specific commit.

    This compares the commit to its parent(s).

    Args:
        repo_path: Path to the git repository
        commit_sha: Commit SHA to analyze (can be short or full)
        include_diff: Include full diff content in Change objects

    Returns:
        ChangeSet with changes in the commit

    Raises:
        GitAnalysisError: If commit doesn't exist or repo is invalid
    """
    repo_path = repo_path.resolve()
    _validate_repo(repo_path)

    # Resolve commit SHA to full SHA
    result = _run_git_command(
        repo_path,
        ["rev-parse", "--verify", commit_sha],
    )
    full_sha = result.stdout.strip()

    # Get changes (commit vs parent)
    # Using commit^! shows changes introduced by just this commit
    result_status = _run_git_command(
        repo_path,
        ["diff-tree", "--no-commit-id", "--name-status", "-r", full_sha],
    )
    result_numstat = _run_git_command(
        repo_path,
        ["diff-tree", "--no-commit-id", "--numstat", "-r", full_sha],
    )

    diff_output = None
    if include_diff:
        result_diff = _run_git_command(
            repo_path,
            ["show", "--format=", full_sha],
        )
        diff_output = result_diff.stdout

    changes = _parse_diff_output(
        repo_path,
        result_status.stdout,
        result_numstat.stdout,
        diff_output,
    )

    # Get parent commit for base_ref
    parent_result = _run_git_command(
        repo_path,
        ["rev-parse", f"{full_sha}^"],
        check=False,  # Initial commits have no parent
    )

    if parent_result.returncode == 0:
        base_ref = parent_result.stdout.strip()
    else:
        # Initial commit - use empty tree
        base_ref = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git empty tree SHA

    # Get commit metadata
    log_result = _run_git_command(
        repo_path,
        ["log", "-1", "--format=%an|%ae|%s|%aI", full_sha],
    )
    log_parts = log_result.stdout.strip().split("|")
    commit_metadata = {}
    if len(log_parts) >= 4:
        commit_metadata = {
            "author_name": log_parts[0],
            "author_email": log_parts[1],
            "subject": log_parts[2],
            "authored_date": log_parts[3],
        }

    return ChangeSet(
        base_ref=base_ref,
        head_ref=full_sha,
        changes=changes,
        repository_root=repo_path,
        metadata={
            "type": "commit",
            "commit_sha": full_sha,
            **commit_metadata,
        },
    )


def analyze_range(
    repo_path: Path,
    base_ref: str,
    head_ref: str,
    include_diff: bool = False,
) -> ChangeSet:
    """
    Analyze changes between two git references.

    This is useful for comparing branches or analyzing PR changes.

    Args:
        repo_path: Path to the git repository
        base_ref: Base reference (commit SHA, branch, tag)
        head_ref: Head reference (commit SHA, branch, tag)
        include_diff: Include full diff content in Change objects

    Returns:
        ChangeSet with changes between the refs

    Raises:
        GitAnalysisError: If refs don't exist or repo is invalid
    """
    repo_path = repo_path.resolve()
    _validate_repo(repo_path)

    # Resolve refs to full SHAs
    base_result = _run_git_command(
        repo_path,
        ["rev-parse", "--verify", base_ref],
    )
    base_sha = base_result.stdout.strip()

    head_result = _run_git_command(
        repo_path,
        ["rev-parse", "--verify", head_ref],
    )
    head_sha = head_result.stdout.strip()

    # Get diff between refs
    result_status = _run_git_command(
        repo_path,
        ["diff", "--name-status", base_sha, head_sha],
    )
    result_numstat = _run_git_command(
        repo_path,
        ["diff", "--numstat", base_sha, head_sha],
    )

    diff_output = None
    if include_diff:
        result_diff = _run_git_command(
            repo_path,
            ["diff", base_sha, head_sha],
        )
        diff_output = result_diff.stdout

    changes = _parse_diff_output(
        repo_path,
        result_status.stdout,
        result_numstat.stdout,
        diff_output,
    )

    # Get merge base to understand the relationship
    merge_base_result = _run_git_command(
        repo_path,
        ["merge-base", base_sha, head_sha],
        check=False,
    )
    merge_base = merge_base_result.stdout.strip() if merge_base_result.returncode == 0 else None

    return ChangeSet(
        base_ref=base_sha,
        head_ref=head_sha,
        changes=changes,
        repository_root=repo_path,
        metadata={
            "type": "range",
            "original_base_ref": base_ref,
            "original_head_ref": head_ref,
            "merge_base": merge_base,
        },
    )


def analyze_pr_changes(
    repo_path: Path,
    base_branch: Optional[str] = None,
    head_branch: Optional[str] = None,
    include_diff: bool = False,
) -> ChangeSet:
    """
    Convenience function for analyzing PR-style changes.

    If base_branch is not specified, uses the default branch.
    If head_branch is not specified, uses the current branch.

    Args:
        repo_path: Path to the git repository
        base_branch: Target branch for the PR (default: main/master)
        head_branch: Source branch for the PR (default: current branch)
        include_diff: Include full diff content in Change objects

    Returns:
        ChangeSet with PR changes

    Raises:
        GitAnalysisError: If branches don't exist or repo is invalid
    """
    repo_path = repo_path.resolve()
    _validate_repo(repo_path)

    if base_branch is None:
        base_branch = get_default_branch(repo_path)

    if head_branch is None:
        head_branch = get_current_branch(repo_path)

    changeset = analyze_range(
        repo_path,
        base_branch,
        head_branch,
        include_diff=include_diff,
    )

    # Update metadata to indicate this is a PR analysis
    changeset.metadata["type"] = "pull_request"
    changeset.metadata["base_branch"] = base_branch
    changeset.metadata["head_branch"] = head_branch

    return changeset


__all__ = [
    "GitAnalysisError",
    "get_current_branch",
    "get_default_branch",
    "analyze_working_changes",
    "analyze_commit",
    "analyze_range",
    "analyze_pr_changes",
]
