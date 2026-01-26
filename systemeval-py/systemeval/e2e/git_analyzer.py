"""
Backward compatibility shim for e2e git_analyzer.

After Phase 2 reorganization, git_analyzer moved to e2e/analysis/git_analyzer.py
This file provides backward compatibility for imports like:
    from systemeval.e2e.git_analyzer import analyze_commit

Prefer importing from systemeval.e2e.analysis.git_analyzer:
    from systemeval.e2e.analysis.git_analyzer import analyze_commit
"""

from .analysis.git_analyzer import (
    GitAnalysisError,
    get_current_branch,
    get_default_branch,
    analyze_working_changes,
    analyze_commit,
    analyze_range,
    analyze_pr_changes,
    _parse_change_type,
    _parse_numstat_line,
    _parse_diff_output,
    _run_git_command,
    _validate_repo,
)

__all__ = [
    "GitAnalysisError",
    "get_current_branch",
    "get_default_branch",
    "analyze_working_changes",
    "analyze_commit",
    "analyze_range",
    "analyze_pr_changes",
    "_parse_change_type",
    "_parse_numstat_line",
    "_parse_diff_output",
    "_run_git_command",
    "_validate_repo",
]
