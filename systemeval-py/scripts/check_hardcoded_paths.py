#!/usr/bin/env python3
"""
Lint check: Prevent hardcoded paths in business logic.

SE-7gk: Architectural Principle - No magic values.

Paths should come from configuration, not be hardcoded in business logic.
This prevents environment-specific paths from breaking portability.

This check flags:
- Hardcoded absolute paths: /Users/, /home/, C:\\, /root/, /var/, /tmp/
- Platform-specific paths: /Applications/, /Library/, /System/

Allowed files:
- config.py, settings.py, constants.py, paths.py, defaults.py (config modules)
- conftest.py (test setup)
- tests/* (test files can use fixture paths)

Allowed contexts:
- Docstrings (documentation examples)
- Comments

Run: python scripts/check_hardcoded_paths.py
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Set


class Violation(NamedTuple):
    file: Path
    line_num: int
    column: int
    line: str
    matched_path: str


# Patterns for detecting hardcoded paths
# Note: These patterns must be specific enough to avoid false positives in regex strings
HARDCODED_PATH_PATTERNS = [
    # Unix absolute paths with user directories (must have actual path content)
    re.compile(r'/(Users|home|root)/[\w.-]+(/[\w.-]+)*'),
    # Windows absolute paths - requires actual directory name after backslash
    # Must match patterns like C:\Users, D:\Program Files, not regex like "e:\s"
    # Requires at least 2 letters after backslash to avoid regex escapes like \s, \d
    re.compile(r'[A-Za-z]:\\[A-Za-z]{2,}[\w\s.-]*'),
    # System paths that shouldn't be hardcoded (must have actual content)
    re.compile(r'/(var|tmp|opt|etc|usr)/(local/)?[\w.-]+(/[\w.-]+)*'),
    # macOS specific system paths
    re.compile(r'/(Applications|Library|System)/[\w\s.-]+'),
]

# Config files where paths are allowed
CONFIG_FILES: Set[str] = {
    "config.py",
    "settings.py",
    "constants.py",
    "paths.py",
    "defaults.py",
    "conftest.py",
}

# Directories where checks are skipped
EXCLUDED_DIRS: Set[str] = {
    "tests",
    "test",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "scripts",  # Lint scripts themselves are allowed to reference paths
}


def is_excluded_file(file_path: Path) -> bool:
    """Check if file should be excluded from checking."""
    # Check filename against config files
    if file_path.name in CONFIG_FILES:
        return True

    # Check if in excluded directory
    for part in file_path.parts:
        if part in EXCLUDED_DIRS:
            return True

    return False


class HardcodedPathVisitor(ast.NodeVisitor):
    """AST visitor to find hardcoded paths, excluding docstrings."""

    def __init__(self, source_lines: List[str]):
        self.source_lines = source_lines
        self.violations: List[Violation] = []
        self._docstring_nodes: Set[int] = set()
        self._mark_docstrings_done = False

    def mark_docstrings(self, tree: ast.AST) -> None:
        """Pre-process AST to mark all docstring nodes."""
        if self._mark_docstrings_done:
            return

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (
                    hasattr(node, 'body')
                    and node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    self._docstring_nodes.add(id(node.body[0].value))

        self._mark_docstrings_done = True

    def visit_Constant(self, node: ast.Constant) -> None:
        """Check string constants for hardcoded paths."""
        if not isinstance(node.value, str):
            return

        # Skip docstrings
        if id(node) in self._docstring_nodes:
            return

        value = node.value

        # Skip short strings (unlikely to be paths)
        if len(value) < 5:
            return

        # Check against path patterns
        for pattern in HARDCODED_PATH_PATTERNS:
            match = pattern.search(value)
            if match:
                # Get line content
                line_content = ""
                if 0 < node.lineno <= len(self.source_lines):
                    line_content = self.source_lines[node.lineno - 1].strip()

                # Skip if it's a comment line
                if line_content.lstrip().startswith("#"):
                    continue

                self.violations.append(Violation(
                    file=Path(""),  # Set by caller
                    line_num=node.lineno,
                    column=node.col_offset,
                    line=line_content,
                    matched_path=match.group(0),
                ))
                break  # One violation per string

        self.generic_visit(node)


def check_file(file_path: Path, project_root: Path) -> List[Violation]:
    """Check a single file for hardcoded path violations."""
    if is_excluded_file(file_path):
        return []

    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    visitor = HardcodedPathVisitor(source_lines)
    visitor.mark_docstrings(tree)
    visitor.visit(tree)

    # Set file path on violations (relative to project root)
    try:
        rel_path = file_path.relative_to(project_root)
    except ValueError:
        rel_path = file_path

    for v in visitor.violations:
        visitor.violations[visitor.violations.index(v)] = Violation(
            file=rel_path,
            line_num=v.line_num,
            column=v.column,
            line=v.line,
            matched_path=v.matched_path,
        )

    return visitor.violations


def main() -> int:
    """Run the hardcoded path check on the systemeval package."""
    # Find project root (directory containing pyproject.toml)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Check systemeval package
    package_dir = project_root / "systemeval"
    if not package_dir.exists():
        print(f"Error: Package directory not found: {package_dir}")
        return 1

    # Find all Python files in the package
    python_files = list(package_dir.rglob("*.py"))

    all_violations: List[Violation] = []

    for file_path in python_files:
        violations = check_file(file_path, project_root)
        all_violations.extend(violations)

    if all_violations:
        print("SE-7gk: Hardcoded paths in business logic")
        print("=" * 60)
        print()
        print("Architectural rule: Paths must come from configuration,")
        print("not be hardcoded in business logic.")
        print()
        print("Violations found:")
        print("-" * 60)

        for v in all_violations:
            print(f"{v.file}:{v.line_num}:{v.column}: hardcoded path '{v.matched_path}'")
            print(f"    {v.line}")
            print()

        print("-" * 60)
        print(f"Total: {len(all_violations)} violation(s)")
        print()
        print("To fix: Move paths to config.py or accept them as parameters.")
        print("Use Path objects from configuration, not string literals.")
        return 1

    print("SE-7gk: No hardcoded path violations found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
