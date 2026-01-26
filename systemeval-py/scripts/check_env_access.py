#!/usr/bin/env python3
"""
Lint check: Prevent direct environment variable access in business logic.

Architectural Principle:
- "No magic values" and "no config discovery"
- Business logic should receive config via dependency injection
- Only entry points (cli.py) and config layers (config.py) may read env vars

This check flags:
- os.environ["KEY"]
- os.environ.get("KEY")
- os.getenv("KEY")
- environ.get patterns

Allowed files:
- cli.py (entry point)
- config.py (config loading layer)
- conftest.py (test setup)
- tests/* (test files can manipulate env for testing)
"""

import re
import sys
from pathlib import Path
from typing import List, NamedTuple


class Violation(NamedTuple):
    file: Path
    line_num: int
    line: str
    pattern: str


# Files where env var access is allowed
ALLOWED_FILES = {
    "cli.py",         # Entry point
    "config.py",      # Config loading layer
    "e2e_config.py",  # E2E config layer
    "conftest.py",    # Test setup
}

# Directories where env var access is allowed
ALLOWED_DIRS = {
    "tests",
}

# Paths (relative from package root) where env var access is allowed
# These are utilities that manage runtime environment setup
ALLOWED_PATHS = {
    "plugins/docker.py",   # Runtime environment detection (is code in Docker?)
    "utils/django.py",     # Django settings module setup (Python env config)
}

# Patterns that indicate env var access for config reading
# Note: Patterns like `env={**os.environ}` for subprocess are allowed
ENV_ACCESS_PATTERNS = [
    # Direct os.environ access for config values
    (r'os\.environ\["[^"]+"\]', "os.environ[KEY]"),
    (r"os\.environ\['[^']+'\]", "os.environ[KEY]"),
    (r'os\.environ\.get\s*\(', "os.environ.get()"),
    (r'os\.getenv\s*\(', "os.getenv()"),
    # Raw environ.get (from os import environ)
    (r'(?<!\*\*)environ\.get\s*\(', "environ.get()"),
    (r'(?<!\*\*)environ\["[^"]+"\]', "environ[KEY]"),
    (r"(?<!\*\*)environ\['[^']+'\]", "environ[KEY]"),
]

# Patterns that are ALLOWED (subprocess env passthrough)
ALLOWED_PATTERNS = [
    r'env\s*=\s*\{\s*\*\*os\.environ',  # env={**os.environ, ...}
    r'env\s*=\s*dict\s*\(\s*os\.environ\s*\)',  # env=dict(os.environ)
    r'full_env\s*=\s*dict\s*\(\s*os\.environ\s*\)',  # full_env=dict(os.environ)
]


def is_allowed_file(file_path: Path) -> bool:
    """Check if file is in the allowed list."""
    # Check filename
    if file_path.name in ALLOWED_FILES:
        return True

    # Check if in allowed directory
    for part in file_path.parts:
        if part in ALLOWED_DIRS:
            return True

    # Check if relative path matches allowed paths
    # Normalize the path to find the package-relative portion
    path_str = str(file_path)
    for allowed_path in ALLOWED_PATHS:
        if path_str.endswith(allowed_path):
            return True

    return False


def is_allowed_pattern(line: str) -> bool:
    """Check if line matches an allowed pattern (subprocess env passthrough)."""
    for pattern in ALLOWED_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def is_docstring_or_example(lines: List[str], line_num: int, line: str) -> bool:
    """Check if line is inside a docstring or is a documentation example."""
    stripped = line.strip()

    # Check for comment markers indicating anti-pattern examples
    anti_pattern_markers = [
        "# NO",
        "# Anti-pattern",
        "# DO NOT",
        "# Wrong",
        "(DO NOT DO)",
        "Anti-pattern",
    ]
    for marker in anti_pattern_markers:
        if marker in line:
            return True

    # Check if we're inside a docstring by counting triple quotes
    # This is a simple heuristic - count unbalanced triple quotes before this line
    content_before = "\n".join(lines[:line_num - 1])
    triple_double = content_before.count('"""')
    triple_single = content_before.count("'''")

    # If odd number of triple quotes, we're inside a docstring
    if triple_double % 2 == 1 or triple_single % 2 == 1:
        return True

    return False


def check_file(file_path: Path) -> List[Violation]:
    """Check a single file for env var access violations."""
    violations = []

    if is_allowed_file(file_path):
        return violations

    try:
        content = file_path.read_text()
    except Exception:
        return violations

    lines = content.splitlines()

    for line_num, line in enumerate(lines, start=1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # Skip allowed patterns (subprocess env passthrough)
        if is_allowed_pattern(line):
            continue

        # Skip docstrings and documentation examples
        if is_docstring_or_example(lines, line_num, line):
            continue

        # Check for violations
        for pattern, description in ENV_ACCESS_PATTERNS:
            if re.search(pattern, line):
                violations.append(Violation(
                    file=file_path,
                    line_num=line_num,
                    line=stripped,
                    pattern=description,
                ))
                break  # One violation per line is enough

    return violations


def main() -> int:
    """Run the env access check on all Python files."""
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
        # Get relative path from package root for cleaner output
        try:
            rel_path = file_path.relative_to(project_root)
        except ValueError:
            rel_path = file_path

        violations = check_file(file_path)
        all_violations.extend(violations)

    if all_violations:
        print("SE-FLW: Environment variable access in business logic")
        print("=" * 60)
        print()
        print("Architectural rule: Business logic must not read environment")
        print("variables directly. Use dependency injection via config.py.")
        print()
        print("Violations found:")
        print("-" * 60)

        for v in all_violations:
            try:
                rel_path = v.file.relative_to(project_root)
            except ValueError:
                rel_path = v.file
            print(f"{rel_path}:{v.line_num}: {v.pattern}")
            print(f"    {v.line}")
            print()

        print("-" * 60)
        print(f"Total: {len(all_violations)} violation(s)")
        print()
        print("To fix: Move env var access to config.py and inject config")
        print("into business logic via constructor or function parameters.")
        return 1

    print("SE-FLW: No environment variable access violations found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
