"""Regex patterns for executor parsing."""
import re
from typing import Callable, Optional

from systemeval.types import TestResult

# Type alias for parser factory function
ParserFactory = Callable[[str, int], Optional[TestResult]]


# ============================================================================
# Test Output Pattern Classes
# ============================================================================
# Organized regex patterns for parsing test framework output.
# Patterns are compiled once at module load for better performance.
# ============================================================================


class PytestPatterns:
    """
    Regex patterns for parsing pytest output.

    Handles multiple pytest output formats:
    - Decorated summary: "====== 10 passed, 1 failed in 5.23s ======"
    - Short summary: "10 passed, 1 failed"
    - Collection errors: "collected 0 items", "ERROR collecting"
    """

    # Full decorated summary line with equals signs
    # Example: "============ 10 passed, 1 failed, 1 error in 5.23s ============"
    FULL_SUMMARY = re.compile(
        r"=+\s+"  # Leading equals followed by whitespace (required)
        r"(?:"  # Start of required test counts group
        r"(?:(?P<warnings>\d+)\s+warnings?,?\s*)?"  # Optional warnings
        r"(?:(?P<passed>\d+)\s+passed(?:,\s*|\s+))?"  # Passed count
        r"(?:(?P<failed>\d+)\s+failed(?:,\s*|\s+))?"  # Failed count
        r"(?:(?P<errors>\d+)\s+errors?(?:,\s*|\s+))?"  # Error count
        r"(?:(?P<skipped>\d+)\s+skipped(?:,\s*|\s+))?"  # Skipped count
        r"(?:(?P<deselected>\d+)\s+deselected(?:,\s*|\s+))?"  # Deselected count
        r")"
        r"(?:in\s+(?P<duration>[\d.]+)s?)?"  # Duration
        r"\s*=+",  # Trailing equals
        re.IGNORECASE
    )

    # Alternative summary line without decoration
    # Example: "10 passed, 1 failed in 5.23s"
    SHORT_SUMMARY = re.compile(
        r"(?P<passed>\d+)\s+passed"
        r"(?:,\s*(?P<failed>\d+)\s+failed)?"
        r"(?:,\s*(?P<errors>\d+)\s+errors?)?"
        r"(?:,\s*(?P<skipped>\d+)\s+skipped)?"
        r"(?:\s+in\s+(?P<duration>[\d.]+)s)?",
        re.IGNORECASE
    )

    # Collection/import errors that prevent test execution
    COLLECTION_ERROR = re.compile(
        r"(?:collected\s+0\s+items|no\s+tests\s+ran|"
        r"ERROR\s+collecting|collection\s+error|"
        r"ModuleNotFoundError|ImportError)",
        re.IGNORECASE
    )


class JestPatterns:
    """
    Regex patterns for parsing Jest output.

    Handles Jest's "Tests: X passed, Y failed, Z total" format.
    Order of passed/failed can vary.
    """

    # Main summary line: "Tests: 5 passed, 1 failed, 6 total"
    SUMMARY = re.compile(
        r"Tests?:\s*"
        r"(?:(?P<passed>\d+)\s+passed,?\s*)?"
        r"(?:(?P<failed>\d+)\s+failed,?\s*)?"
        r"(?:(?P<skipped>\d+)\s+(?:skipped|todo),?\s*)?"
        r"(?P<total>\d+)\s+total",
        re.IGNORECASE
    )

    # Time line: "Time: 5.23s"
    TIME = re.compile(r"Time:\s*([\d.]+)\s*s", re.IGNORECASE)


class PlaywrightPatterns:
    """
    Regex patterns for parsing Playwright test output.

    Playwright uses parentheses around duration: "5 passed (10s)"
    This distinguishes it from pytest's "5 passed in 10s" format.
    """

    # Summary with duration in parentheses: "5 passed (10s)"
    SUMMARY = re.compile(
        r"(?P<passed>\d+)\s+passed\s*\(\s*(?P<duration>[\d.]+)\s*(?:s|ms)\s*\)",
        re.IGNORECASE
    )

    # Failed/flaky count: "2 failed" or "1 flaky"
    FAILED = re.compile(
        r"(?P<failed>\d+)\s+(?:failed|flaky)",
        re.IGNORECASE
    )

    # Skipped count: "3 skipped"
    SKIPPED = re.compile(
        r"(?P<skipped>\d+)\s+skipped",
        re.IGNORECASE
    )


class MochaPatterns:
    """
    Regex patterns for parsing Mocha test output.

    Mocha uses "passing" instead of "passed": "5 passing (2s)"
    """

    # Passing count with duration: "5 passing (2s)"
    PASSING = re.compile(r"(\d+)\s+passing\s*\(([^)]+)\)", re.IGNORECASE)

    # Failing count: "2 failing"
    FAILING = re.compile(r"(\d+)\s+failing", re.IGNORECASE)

    # Pending/skipped count: "1 pending"
    PENDING = re.compile(r"(\d+)\s+pending", re.IGNORECASE)


class GoTestPatterns:
    """
    Regex patterns for parsing Go test output.

    Go test uses package-level pass/fail indicators:
    - "ok  package/name  1.234s" for passing
    - "FAIL package/name" for failing
    - "?   package/name  [no test files]" for skipped
    """

    # Package passed: "ok  package/name  1.234s"
    PASS = re.compile(r"^\s*ok\s+\S+\s+([\d.]+)s", re.MULTILINE)

    # Package failed: "FAIL package/name"
    FAIL = re.compile(r"^\s*FAIL\s+\S+", re.MULTILINE)

    # Package skipped (no test files): "?   package/name  [no test files]"
    SKIP = re.compile(r"^\s*\?\s+\S+\s+\[no test files\]", re.MULTILINE)


class GenericPatterns:
    """
    Generic regex patterns for parsing unknown test framework output.

    Used as a fallback when framework-specific patterns don't match.
    These patterns look for common test result keywords.
    """

    # Count of passed tests: "10 passed", "5 passing", "3 succeeded"
    PASSED = re.compile(r"(\d+)\s+(?:passed|passing|succeeded|ok)\b", re.IGNORECASE)

    # Count of failed tests: "2 failed", "1 failing", "3 errors"
    FAILED = re.compile(r"(\d+)\s+(?:failed|failing|failure|errors?)\b", re.IGNORECASE)

    # Count of skipped tests: "1 skipped", "2 pending", "0 ignored"
    SKIPPED = re.compile(r"(\d+)\s+(?:skipped|pending|ignored)\b", re.IGNORECASE)

    # Duration: "in 5.23s", "time: 10.5 seconds"
    DURATION = re.compile(r"(?:in|time[:\s]*)\s*([\d.]+)\s*s(?:econds?)?", re.IGNORECASE)


