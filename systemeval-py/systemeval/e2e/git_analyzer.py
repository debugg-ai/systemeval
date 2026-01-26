"""
Backward compatibility shim for e2e git_analyzer.

After Phase 2 reorganization, git_analyzer moved to e2e/analysis/git_analyzer.py
This file provides backward compatibility for imports like:
    from systemeval.e2e.git_analyzer import GitAnalyzer

Prefer importing from systemeval.e2e.analysis:
    from systemeval.e2e.analysis import GitAnalyzer
"""

from .analysis.git_analyzer import (
    GitAnalyzer,
    RepositoryState,
    FileChange,
    parse_git_diff,
)

__all__ = [
    "GitAnalyzer",
    "RepositoryState",
    "FileChange",
    "parse_git_diff",
]
