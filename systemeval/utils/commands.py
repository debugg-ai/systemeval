"""
Command building utilities for test execution.

Provides shared logic for constructing test commands across different environments.
"""
from typing import List, Optional, Union


def build_test_command(
    base_command: Union[str, List[str]],
    suite: Optional[str] = None,
    category: Optional[str] = None,
    verbose: bool = False,
) -> Union[str, List[str]]:
    """
    Build a test command with optional filters.

    Supports various test frameworks and custom scripts:
    - pytest: adds -m flags for suite/category, -v for verbose
    - npm test/jest: adds --testPathPattern for suite
    - playwright: adds --grep for suite
    - Shell scripts: prefixes with SUITE/CATEGORY env vars, appends -v

    Args:
        base_command: The base test command (string or list of commands)
        suite: Optional test suite filter (e.g., "unit", "integration")
        category: Optional test category filter
        verbose: Whether to enable verbose output

    Returns:
        The modified command string or list of commands
    """
    # Handle list of commands - return as-is (no modifications)
    if isinstance(base_command, list):
        return base_command

    # Handle single command string
    cmd = base_command

    # Check if it's a script (starts with ./ or /)
    if cmd.startswith("./") or cmd.startswith("/"):
        # For scripts, pass filters as environment variables
        if suite:
            cmd = f"SUITE={suite} {cmd}"
        if category:
            cmd = f"CATEGORY={category} {cmd}"
        if verbose:
            cmd = f"{cmd} -v"
        return cmd

    # For standard test frameworks, add appropriate flags
    if "pytest" in cmd:
        if suite:
            cmd = f"{cmd} -m {suite}"
        if category:
            cmd = f"{cmd} -m {category}"
        if verbose and "-v" not in cmd:
            cmd = f"{cmd} -v"
    elif "npm test" in cmd or "jest" in cmd:
        if suite:
            cmd = f"{cmd} --testPathPattern={suite}"
    elif "playwright" in cmd:
        if suite:
            cmd = f"{cmd} --grep {suite}"

    return cmd
