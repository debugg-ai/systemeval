"""Tests for the hardcoded paths lint check."""

import tempfile
from pathlib import Path

import pytest

# Import the check functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from check_hardcoded_paths import (
    check_file,
    is_excluded_file,
    HARDCODED_PATH_PATTERNS,
)


class TestIsExcludedFile:
    """Tests for file exclusion logic."""

    def test_config_files_excluded(self):
        """Config files should be excluded."""
        assert is_excluded_file(Path("config.py"))
        assert is_excluded_file(Path("settings.py"))
        assert is_excluded_file(Path("constants.py"))
        assert is_excluded_file(Path("paths.py"))
        assert is_excluded_file(Path("defaults.py"))
        assert is_excluded_file(Path("conftest.py"))

    def test_test_directories_excluded(self):
        """Test directories should be excluded."""
        assert is_excluded_file(Path("tests/test_foo.py"))
        assert is_excluded_file(Path("test/test_bar.py"))

    def test_business_logic_not_excluded(self):
        """Business logic files should not be excluded."""
        assert not is_excluded_file(Path("cli.py"))
        assert not is_excluded_file(Path("adapters/base.py"))
        assert not is_excluded_file(Path("core/evaluation.py"))


class TestHardcodedPathPatterns:
    """Tests for the hardcoded path detection patterns."""

    def test_unix_user_paths_detected(self):
        """Unix user paths should be detected."""
        test_cases = [
            "/Users/john/project",
            "/home/user/code",
            "/root/scripts",
        ]
        for path in test_cases:
            matched = any(p.search(path) for p in HARDCODED_PATH_PATTERNS)
            assert matched, f"Expected to detect: {path}"

    def test_windows_paths_detected(self):
        """Windows paths should be detected."""
        test_cases = [
            "C:\\Users\\John",
            "D:\\Program Files",
            "E:\\Projects\\code",
        ]
        for path in test_cases:
            matched = any(p.search(path) for p in HARDCODED_PATH_PATTERNS)
            assert matched, f"Expected to detect: {path}"

    def test_system_paths_detected(self):
        """System paths should be detected."""
        test_cases = [
            "/var/log/app",
            "/tmp/cache",
            "/etc/config",
            "/opt/software",
            "/usr/local/bin",
        ]
        for path in test_cases:
            matched = any(p.search(path) for p in HARDCODED_PATH_PATTERNS)
            assert matched, f"Expected to detect: {path}"

    def test_macos_paths_detected(self):
        """macOS system paths should be detected."""
        test_cases = [
            "/Applications/App.app",
            "/Library/Preferences",
            "/System/Library",
        ]
        for path in test_cases:
            matched = any(p.search(path) for p in HARDCODED_PATH_PATTERNS)
            assert matched, f"Expected to detect: {path}"

    def test_regex_escapes_not_detected(self):
        """Regex escape sequences should not trigger false positives."""
        test_cases = [
            r"Time:\s*",  # Contains e:\s but it's regex
            r"e:\d+",     # Contains e:\d but it's regex
            r"match:\w+", # Contains h:\w but it's regex
        ]
        for pattern in test_cases:
            matched = any(p.search(pattern) for p in HARDCODED_PATH_PATTERNS)
            assert not matched, f"Should not detect regex pattern: {pattern}"

    def test_relative_paths_not_detected(self):
        """Relative paths should not be detected."""
        test_cases = [
            "tests/fixtures",
            "./config",
            "../parent",
            "src/main.py",
        ]
        for path in test_cases:
            matched = any(p.search(path) for p in HARDCODED_PATH_PATTERNS)
            assert not matched, f"Should not detect relative path: {path}"


class TestCheckFile:
    """Tests for the file checking functionality."""

    def test_docstrings_not_flagged(self):
        """Paths in docstrings should not be flagged."""
        code = '''
def example():
    """
    Example usage:
        path = Path("/home/user/project")
    """
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            violations = check_file(Path(f.name), Path(f.name).parent)
            assert len(violations) == 0

    def test_hardcoded_path_in_code_flagged(self):
        """Hardcoded paths in code should be flagged."""
        code = '''
def get_config():
    return "/home/user/config.yaml"
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            violations = check_file(Path(f.name), Path(f.name).parent)
            assert len(violations) == 1
            assert "/home/user" in violations[0].matched_path

    def test_comments_not_flagged(self):
        """Paths in comments should not be flagged."""
        code = '''
# Config file is at /home/user/config.yaml
def get_config():
    pass
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            violations = check_file(Path(f.name), Path(f.name).parent)
            assert len(violations) == 0

    def test_path_objects_flagged(self):
        """Path() calls with hardcoded paths should be flagged."""
        code = '''
from pathlib import Path

config_path = Path("/Users/john/project/config.yaml")
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            violations = check_file(Path(f.name), Path(f.name).parent)
            assert len(violations) == 1
