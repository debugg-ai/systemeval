"""
Test result parsers for various testing frameworks.

Provides:
- Framework-specific parsers (Pytest, Jest, Playwright, Mocha, Go)
- GenericResultParser: Fallback parser using generic patterns
- TestResultAggregator: Orchestrates parsing strategy selection
"""
from typing import List, Optional

from systemeval.types import TestResult
from systemeval.environments.executor.patterns import (
    PytestPatterns,
    JestPatterns,
    PlaywrightPatterns,
    MochaPatterns,
    GoTestPatterns,
    GenericPatterns,
)


class PytestResultParser:
    """Parser for pytest output format."""

    @property
    def name(self) -> str:
        return "pytest"

    def can_parse(self, output: str) -> bool:
        """Check if output looks like pytest output."""
        return bool(
            PytestPatterns.FULL_SUMMARY.search(output)
            or PytestPatterns.SHORT_SUMMARY.search(output)
            or PytestPatterns.COLLECTION_ERROR.search(output)
        )

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """Parse pytest output format."""
        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        duration = 0.0
        found = False

        # Try the full decorated summary line first
        match = PytestPatterns.FULL_SUMMARY.search(output)
        if match:
            groups = match.groupdict()
            passed = int(groups.get("passed") or 0)
            failed = int(groups.get("failed") or 0)
            errors = int(groups.get("errors") or 0)
            skipped = int(groups.get("skipped") or 0)
            if groups.get("duration"):
                duration = float(groups["duration"])
            found = True
        else:
            # Try the short summary format
            match = PytestPatterns.SHORT_SUMMARY.search(output)
            if match:
                groups = match.groupdict()
                passed = int(groups.get("passed") or 0)
                failed = int(groups.get("failed") or 0)
                errors = int(groups.get("errors") or 0)
                skipped = int(groups.get("skipped") or 0)
                if groups.get("duration"):
                    duration = float(groups["duration"])
                found = True

        # Check for collection errors
        if PytestPatterns.COLLECTION_ERROR.search(output):
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=duration,
                exit_code=exit_code,
                parsed_from="pytest",
                parsing_warning="Collection error detected",
            )

        if not found:
            return None

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
            parsed_from="pytest",
        )


class JestResultParser:
    """Parser for Jest output format."""

    @property
    def name(self) -> str:
        return "jest"

    def can_parse(self, output: str) -> bool:
        """Check if output looks like Jest output."""
        return bool(JestPatterns.SUMMARY.search(output))

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """Parse Jest output format."""
        match = JestPatterns.SUMMARY.search(output)
        if not match:
            return None

        groups = match.groupdict()
        passed = int(groups.get("passed") or 0)
        failed = int(groups.get("failed") or 0)
        skipped = int(groups.get("skipped") or 0)

        duration = 0.0
        time_match = JestPatterns.TIME.search(output)
        if time_match:
            duration = float(time_match.group(1))

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
            parsed_from="jest",
        )


class PlaywrightResultParser:
    """Parser for Playwright output format."""

    @property
    def name(self) -> str:
        return "playwright"

    def can_parse(self, output: str) -> bool:
        """Check if output looks like Playwright output."""
        return bool(PlaywrightPatterns.SUMMARY.search(output))

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """Parse Playwright output format."""
        match = PlaywrightPatterns.SUMMARY.search(output)
        if not match:
            return None

        groups = match.groupdict()
        passed = int(groups.get("passed") or 0)
        duration = 0.0
        if groups.get("duration"):
            dur_str = groups["duration"]
            dur_val = float(dur_str)
            # If duration > 1000, assume milliseconds
            duration = dur_val / 1000 if dur_val > 1000 else dur_val

        failed = 0
        failed_match = PlaywrightPatterns.FAILED.search(output)
        if failed_match:
            failed = int(failed_match.group("failed"))

        skipped = 0
        skipped_match = PlaywrightPatterns.SKIPPED.search(output)
        if skipped_match:
            skipped = int(skipped_match.group("skipped"))

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
            parsed_from="playwright",
        )


class MochaResultParser:
    """Parser for Mocha output format."""

    @property
    def name(self) -> str:
        return "mocha"

    def can_parse(self, output: str) -> bool:
        """Check if output looks like Mocha output."""
        return bool(MochaPatterns.PASSING.search(output))

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """Parse Mocha output format."""
        passing_match = MochaPatterns.PASSING.search(output)
        if not passing_match:
            return None

        passed = int(passing_match.group(1))
        duration_str = passing_match.group(2)

        # Parse duration (could be "2s", "500ms", etc.)
        duration = 0.0
        if "ms" in duration_str:
            duration = float(duration_str.replace("ms", "").strip()) / 1000
        elif "s" in duration_str:
            duration = float(duration_str.replace("s", "").strip())

        failed = 0
        failing_match = MochaPatterns.FAILING.search(output)
        if failing_match:
            failed = int(failing_match.group(1))

        skipped = 0
        pending_match = MochaPatterns.PENDING.search(output)
        if pending_match:
            skipped = int(pending_match.group(1))

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
            parsed_from="mocha",
        )


class GoTestResultParser:
    """Parser for Go test output format."""

    @property
    def name(self) -> str:
        return "go"

    def can_parse(self, output: str) -> bool:
        """Check if output looks like Go test output."""
        return bool(
            GoTestPatterns.PASS.search(output)
            or GoTestPatterns.FAIL.search(output)
        )

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """Parse Go test output format."""
        pass_matches = GoTestPatterns.PASS.findall(output)
        fail_matches = GoTestPatterns.FAIL.findall(output)
        skip_matches = GoTestPatterns.SKIP.findall(output)

        if not pass_matches and not fail_matches:
            return None

        passed = len(pass_matches)
        failed = len(fail_matches)
        skipped = len(skip_matches)

        # Sum up durations from all passing packages
        duration = sum(float(d) for d in pass_matches)

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
            parsed_from="go",
        )


class GenericResultParser:
    """Fallback parser using generic patterns."""

    @property
    def name(self) -> str:
        return "generic"

    def can_parse(self, output: str) -> bool:
        """Generic parser can always try to parse."""
        return bool(
            GenericPatterns.PASSED.search(output)
            or GenericPatterns.FAILED.search(output)
        )

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """Parse output using generic patterns as last resort."""
        passed = 0
        failed = 0
        skipped = 0
        duration = 0.0
        found = False

        # Look for passed counts
        passed_matches = GenericPatterns.PASSED.findall(output)
        if passed_matches:
            # Take the largest number found (usually the total)
            passed = max(int(m) for m in passed_matches)
            found = True

        # Look for failed counts
        failed_matches = GenericPatterns.FAILED.findall(output)
        if failed_matches:
            failed = max(int(m) for m in failed_matches)
            found = True

        # Look for skipped counts
        skipped_matches = GenericPatterns.SKIPPED.findall(output)
        if skipped_matches:
            skipped = max(int(m) for m in skipped_matches)
            found = True

        # Look for duration
        duration_match = GenericPatterns.DURATION.search(output)
        if duration_match:
            duration = float(duration_match.group(1))

        if not found:
            return None

        return TestResult(
            passed=passed,
            failed=failed,
            errors=0,
            skipped=skipped,
            duration=duration,
            exit_code=exit_code,
            parsed_from="generic",
        )


# Global parser registry - ordered by specificity (most specific first)
# More specific patterns (Jest "Tests:", Go "ok\s+\S+") should come first
# to avoid false matches by generic patterns
DEFAULT_PARSERS: List["ResultParserProtocol"] = [
    JestResultParser(),      # Has specific "Tests:" prefix
    GoTestResultParser(),    # Has specific "ok" at line start
    MochaResultParser(),     # Has specific "passing (" format
    PlaywrightResultParser(),  # Has specific "passed (Xs)" format
    PytestResultParser(),    # Has decorated lines or simple format
    GenericResultParser(),   # Fallback patterns
]


class TestResultAggregator:
    """
    Aggregates parsing strategies to extract test results.

    Parsing priority:
    1. Structured JSON output (pytest-json-report, jest --json)
    2. Framework-specific regex patterns (pytest, jest, playwright, mocha, go)
    3. Generic patterns
    4. Fallback based on exit code (with warning)
    """

    def __init__(self, parsers: Optional[List["ResultParserProtocol"]] = None):
        self.parsers = parsers or DEFAULT_PARSERS

    def parse(
        self,
        output: str,
        exit_code: int,
        json_output: Optional[str] = None,
    ) -> TestResult:
        """
        Parse test output to extract results.

        Args:
            output: Test command stdout/stderr
            exit_code: Command exit code
            json_output: Optional JSON output from structured reporters

        Returns:
            TestResult with parsed counts and metadata
        """
        # Try structured JSON output first (most reliable)
        if json_output:
            from systemeval.environments.executor.impl.json_parser import JsonResultParser
            json_parser = JsonResultParser()
            if json_parser.can_parse(json_output):
                result = json_parser.parse(json_output, exit_code)
                if result:
                    return result

        # Look for embedded JSON in output (some reporters embed it)
        from systemeval.environments.executor.impl.json_parser import EmbeddedJsonParser
        embedded_parser = EmbeddedJsonParser()
        if embedded_parser.can_parse(output):
            json_result = embedded_parser.parse(output, exit_code)
            if json_result:
                return json_result

        # Try framework-specific parsers in order of specificity
        for parser in self.parsers:
            if parser.can_parse(output):
                result = parser.parse(output, exit_code)
                if result:
                    return result

        # Fallback: couldn't parse output
        return self._create_fallback_result(output, exit_code)

    def _create_fallback_result(
        self,
        output: str,
        exit_code: int,
    ) -> TestResult:
        """
        Create a fallback result when output cannot be parsed.

        When exit_code == 0 but output is unrecognized:
        - Assume 1 passed with a warning

        When exit_code != 0 and output is unrecognized:
        - Set errors=1 (not failed) to trigger ERROR verdict
        - This prevents false positives from guessed test counts
        """
        if exit_code == 0:
            return TestResult(
                passed=1,
                failed=0,
                errors=0,
                skipped=0,
                duration=0.0,
                exit_code=exit_code,
                parsed_from="fallback",
                parsing_warning=(
                    "Output format not recognized. "
                    "Assumed 1 test passed based on exit code 0. "
                    "Consider using structured output (--json-report for pytest, --json for jest)."
                ),
            )
        else:
            # Non-zero exit code with unrecognized output -> ERROR, not FAIL
            return TestResult(
                passed=0,
                failed=0,
                errors=1,  # This triggers ERROR verdict in TestResult.verdict
                skipped=0,
                duration=0.0,
                exit_code=exit_code,
                parsed_from="fallback",
                parsing_warning=(
                    f"Output format not recognized and command failed (exit code {exit_code}). "
                    "Cannot determine actual test counts. Reporting as ERROR. "
                    "Consider using structured output (--json-report for pytest, --json for jest)."
                ),
            )
